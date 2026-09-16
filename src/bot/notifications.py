import asyncio
import io
import logging
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence

import httpx
from PIL import Image, UnidentifiedImageError
from telegram import Bot
from telegram.error import BadRequest, NetworkError, RetryAfter, TelegramError
from models import UserSubscription

from bot.templates import format_multiple_price_drops_messages, format_multiple_new_cars_messages, \
    format_price_drops_message, format_separate_new_car_message, get_drop_percent, absolute_url
from models import Car

from bot.templates import PriceDrop

from bot.templates import get_new_cars_title

from config import Config

logger = logging.getLogger(__name__)

# Telegram просит не чаще одного сообщения в секунду в один чат: пачка
# без пауз заканчивается таймаутом или RetryAfter на одном из сообщений.
SEND_DELAY_SECONDS = 1
SEND_RETRIES = 3
SEND_RETRY_DELAY_SECONDS = 3
# стандартные 5 секунд python-telegram-bot при пачке отправок не хватает
SEND_READ_TIMEOUT_SECONDS = 20

# Машины идут отдельными сообщениями с фото — их можно переслать и найти
# по хэштегу. При всплеске (распродажа, первый запуск после простоя)
# остальные уходят сводкой, чтобы не растягивать отправку и не заваливать тему.
MAX_SEPARATE_MESSAGES = 20
# место под подпись "Часть N из M" в сообщении сводки
PART_LABEL_RESERVE = 40
# лимит Telegram на подпись к фото
CAPTION_LIMIT = 1024
IMAGE_TIMEOUT_SECONDS = 15
IMAGE_MAX_BYTES = 5 * 1024 * 1024


def _to_jpeg(content: bytes) -> bytes:
    """Один из источников отдаёт картинки в WebP. Чтобы не зависеть от того,
    как Telegram обработает этот формат в фото, отправляем всё как JPEG."""
    with Image.open(io.BytesIO(content)) as image:
        if image.format == 'JPEG':
            return content
        buffer = io.BytesIO()
        image.convert('RGB').save(buffer, format='JPEG', quality=90)
        return buffer.getvalue()


def _extract_price(price_str: str) -> int:
    """Извлечение числовой цены из строки"""
    if not price_str:
        return 0
    clean_price = ''.join(filter(str.isdigit, price_str))
    return int(clean_price) if clean_price else 0


def prepare_message(messages: list, max_length: int = 4096) -> list:
    """
        Разбивает список сообщений на части, не превышающие max_length символов.
        Если одно сообщение больше лимита - разбивает его на части.
        """
    final_messages = []
    current_batch = []
    current_length = 0
    separator = "\n\n"
    separator_length = len(separator)

    for message in messages:
        message_length = len(message)

        # Если одно сообщение больше лимита - разбиваем его
        if message_length > max_length:
            # Сохраняем текущую группу
            if current_batch:
                final_messages.append(separator.join(current_batch))
                current_batch = []
                current_length = 0

            # Разбиваем длинное сообщение на части
            for i in range(0, message_length, max_length):
                final_messages.append(message[i:i + max_length])
            continue

        # Проверяем, поместится ли сообщение в текущую группу
        needed_length = message_length
        if current_batch:  # Если не первое сообщение, добавляем разделитель
            needed_length += separator_length

        if current_length + needed_length <= max_length:
            current_batch.append(message)
            current_length += needed_length
        else:
            # Сохраняем текущую группу и начинаем новую
            if current_batch:
                final_messages.append(separator.join(current_batch))
            current_batch = [message]
            current_length = message_length

    # Добавляем последнюю группу
    if current_batch:
        final_messages.append(separator.join(current_batch))

    return final_messages


class NotificationManager:
    def __init__(self, bot: Bot, db_session):
        self.bot = bot
        self.db_session = db_session()

    async def notify_price_drop(self, price_drops: List[PriceDrop]):
        """Уведомление о снижении цены: сначала самые большие скидки"""
        drops = [drop for drop in price_drops if get_drop_percent(drop) >= Config.NOTIFY_PRICE_DROP_PERCENT]
        if len(drops) < len(price_drops):
            logger.info(f"Снижений меньше {Config.NOTIFY_PRICE_DROP_PERCENT}%: "
                        f"{len(price_drops) - len(drops)} — без уведомления")
        if not drops:
            return

        drops.sort(key=get_drop_percent, reverse=True)
        await self._send_separately(
            message_thread_id=Config.PRICE_DROP_THREAD_ID,
            items=drops,
            car_of=lambda drop: drop.car,
            format_one=format_price_drops_message,
            format_rest=lambda rest: format_multiple_price_drops_messages(rest, more=True),
            silent=False,
        )

    async def notify_new_car(self, cars: List[Car]):
        """Уведомление о новом автомобиле"""
        await self._send_separately(
            message_thread_id=Config.NEW_THREAD_ID,
            items=cars,
            car_of=lambda car: car,
            format_one=format_separate_new_car_message,
            format_rest=lambda rest: format_multiple_new_cars_messages(rest, more=True),
            # новые приходят весь рабочий день — без звука;
            # снижения цен редкие и важные, их оставляем со звуком
            silent=True,
        )

    async def _send_separately(self, message_thread_id: int, items: Sequence, car_of: Callable,
                               format_one: Callable, format_rest: Callable, silent: bool):
        separate_items = items[:MAX_SEPARATE_MESSAGES]
        rest_items = items[MAX_SEPARATE_MESSAGES:]

        failed = 0
        for index, item in enumerate(separate_items):
            if index:
                await asyncio.sleep(SEND_DELAY_SECONDS)
            message = format_one(item)
            photo = await self._download_photo(car_of(item)) if len(message) <= CAPTION_LIMIT else None
            if not await self._send_one(message_thread_id, message, photo, silent=silent):
                failed += 1
        if failed:
            logger.error(f"Не отправлено {failed} из {len(separate_items)} сообщений, thread={message_thread_id}")

        if rest_items:
            await asyncio.sleep(SEND_DELAY_SECONDS)
            await self._send_digest(message_thread_id, format_rest(rest_items), silent)

    async def _send_digest(self, message_thread_id: int, messages: list, silent: bool):
        """Сводка из многих машин. Превью ссылки в ней отключаем: Telegram
        строит его по первой ссылке, то есть показал бы случайную машину."""
        parts = prepare_message(messages, max_length=4096 - PART_LABEL_RESERVE)
        if len(parts) > 1:
            # заголовок есть только у первой части — остальным нужен контекст
            parts = [f"{part}\n\n<i>Часть {index} из {len(parts)}</i>"
                     for index, part in enumerate(parts, start=1)]
        await self._send_message(message_thread_id, parts, silent=silent, preview=False)

    async def _send_message(self, message_thread_id: int, messages: list, silent=False, preview=True):
        """Отправка сообщений по одному: сбой одного не отменяет остальные —
        машины к этому моменту уже записаны в базу, и повторно как новые
        они не придут."""
        failed = 0
        for index, message in enumerate(messages):
            if index:
                await asyncio.sleep(SEND_DELAY_SECONDS)
            if not await self._send_one(message_thread_id, message, silent=silent, preview=preview):
                failed += 1

        if failed:
            logger.error(f"Не отправлено {failed} из {len(messages)} сообщений, thread={message_thread_id}")

    async def _download_photo(self, car: Car) -> Optional[bytes]:
        if not car.image_url:
            return None
        url = absolute_url(car, car.image_url)
        try:
            async with httpx.AsyncClient(headers=Config.HEADERS, timeout=IMAGE_TIMEOUT_SECONDS,
                                         follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
            if len(response.content) > IMAGE_MAX_BYTES:
                logger.warning(f"Фото больше {IMAGE_MAX_BYTES // 1024 // 1024} МБ, отправим без него: {url}")
                return None
            return await asyncio.to_thread(_to_jpeg, response.content)
        except (httpx.HTTPError, OSError, UnidentifiedImageError) as e:
            # без фото уведомление всё равно уйдёт текстом
            logger.warning(f"Не удалось загрузить фото {url}: {e}")
            return None

    async def _send_one(self, message_thread_id: int, message: str, photo: Optional[bytes] = None,
                        silent=False, preview=True) -> bool:
        for attempt in range(1, SEND_RETRIES + 1):
            try:
                logger.info(f"Отправка{' с фото' if photo else ''}: thread={message_thread_id}, len={len(message)}")
                common = dict(
                    chat_id=Config.CHANNEL_CHAT_ID,
                    # 0 означает "тема не задана": в обычную группу или канал
                    # message_thread_id слать нельзя, Telegram ответит ошибкой
                    message_thread_id=message_thread_id or None,
                    parse_mode='HTML',
                    disable_notification=silent,
                    read_timeout=SEND_READ_TIMEOUT_SECONDS,
                    write_timeout=SEND_READ_TIMEOUT_SECONDS,
                )
                if photo:
                    result = await self.bot.send_photo(photo=photo, caption=message, **common)
                else:
                    result = await self.bot.send_message(text=message, disable_web_page_preview=not preview, **common)
                logger.info(f"Отправлено: msg_id={result.message_id}, thread={result.message_thread_id}")
                return True

            except RetryAfter as e:
                # e удаляется по выходу из except — сохраняем для лога ниже
                error, delay = e, e.retry_after
            except BadRequest as e:
                if photo:
                    # фото не приняли — уведомление важнее картинки
                    logger.warning(f"Фото не принято ({e}), отправляем текстом")
                    return await self._send_one(message_thread_id, message, silent=silent, preview=preview)
                # наследник NetworkError, но повтор не поможет: неверный чат, разметка и т.п.
                logger.error(f"Ошибка отправки: {e}")
                return False
            except NetworkError as e:
                # При таймауте Telegram мог сообщение всё же принять, и повтор
                # даст дубль. Дубль в канале лучше потерянного уведомления.
                error, delay = e, SEND_RETRY_DELAY_SECONDS * attempt
            except TelegramError as e:
                logger.error(f"Ошибка отправки: {e}")
                return False

            if attempt == SEND_RETRIES:
                logger.error(f"Ошибка отправки после {SEND_RETRIES} попыток: {error}")
                return False
            logger.warning(f"Попытка {attempt} из {SEND_RETRIES} не удалась ({error}), повтор через {delay} с")
            await asyncio.sleep(delay)

        return False
