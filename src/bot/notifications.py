import logging
from telegram import Bot
from telegram.error import TelegramError
from models import UserSubscription
from config import Config

from src.bot.templates import format_new_car_message, format_price_drop_message

logger = logging.getLogger(__name__)


def _extract_price(price_str: str) -> int:
    """Извлечение числовой цены из строки"""
    if not price_str:
        return 0
    clean_price = ''.join(filter(str.isdigit, price_str))
    return int(clean_price) if clean_price else 0


def _calculate_drop_percent(old_price: str, new_price: str):
    try:
        # Убираем всё кроме цифр
        old_clean = ''.join(c for c in old_price if c.isdigit())
        new_clean = ''.join(c for c in new_price if c.isdigit())

        int_old_price = int(old_clean)
        int_new_price = int(new_clean)

        if int_old_price > 0:
            return (int_old_price - int_new_price) / int_old_price * 100

    except (ValueError, ZeroDivisionError):
        pass

    return 0


class NotificationManager:
    def __init__(self, bot: Bot, db_session):
        self.bot = bot
        self.db_session = db_session()

    async def notify_price_drop(self, car, old_price: str):
        """Уведомление о снижении цены"""
        subscribers = self.db_session.query(UserSubscription).filter(
            UserSubscription.is_active,
            UserSubscription.notify_price_drops
        ).all()

        new_price = car.price
        message = format_price_drop_message(car, old_price, new_price)

        for subscriber in subscribers:
            await self._send_message(subscriber.chat_id, message)

    async def notify_new_car(self, car):
        """Уведомление о новом автомобиле"""
        subscribers = self.db_session.query(UserSubscription).filter(
            UserSubscription.is_active,
            UserSubscription.notify_new_cars
        ).all()

        message = format_new_car_message(car)

        for subscriber in subscribers:
            await self._send_message(subscriber.chat_id, message)

    async def _send_message(self, chat_id: str, message: str):
        """Отправка сообщения с обработкой ошибок"""
        print(f"send message {len(message)}")
        try:
            await self.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode='HTML',
                disable_web_page_preview=False
            )
            logger.info(f"Уведомление отправлено пользователю {chat_id}")
        except TelegramError as e:
            logger.error(f"Ошибка отправки уведомления пользователю {chat_id}: {e}")
