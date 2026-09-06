import logging
from dataclasses import dataclass
from typing import List

from telegram import Bot
from telegram.error import TelegramError
from models import UserSubscription

from bot.templates import format_multiple_price_drops_messages, format_multiple_new_cars_messages
from models import Car

from bot.templates import PriceDrop

from bot.templates import get_new_cars_title

from config import Config

logger = logging.getLogger(__name__)


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
        """Уведомление о снижении цены"""
        messages = format_multiple_price_drops_messages(price_drops)
        await self._send_message(Config.PRICE_DROP_THREAD_ID, prepare_message(messages))


    async def notify_new_car(self, cars: List[Car]):
        """Уведомление о новом автомобиле"""
        messages = format_multiple_new_cars_messages(cars)
        await self._send_message(Config.NEW_THREAD_ID, prepare_message(messages))

    async def _send_message(self, message_thread_id: int, messages: list):
        """Отправка сообщения с обработкой ошибок"""
        try:
            for message in messages:
                logger.info(f"Отправка: thread={message_thread_id}, len={len(message)}")
                result = await self.bot.send_message(
                    chat_id=Config.CHANNEL_CHAT_ID,
                    # 0 означает "тема не задана": в обычную группу или канал
                    # message_thread_id слать нельзя, Telegram ответит ошибкой
                    message_thread_id=message_thread_id or None,
                    text=message,
                    parse_mode='HTML',
                    disable_web_page_preview=False
                )
                logger.info(f"Отправлено: msg_id={result.message_id}, thread={result.message_thread_id}")
        except TelegramError as e:
            logger.error(f"Ошибка отправки: {e}")
