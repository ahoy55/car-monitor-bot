import logging
from datetime import datetime

import pytz
from telegram import Update
from telegram.ext import ContextTypes

from config import Config

logger = logging.getLogger(__name__)
timezone = pytz.timezone('Europe/Moscow')


def _describe_interval(second_field: str) -> str:
    """Поле second cron-триггера человеческими словами."""
    if second_field.isdigit():
        return "раз в минуту"
    if second_field.startswith("*/") and second_field[2:].isdigit():
        return f"каждые {second_field[2:]} сек."
    return f"по расписанию second={second_field}"


class BotHandlers:
    def __init__(self, db_session):
        self.db_session = db_session()

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start {password} """
        user = update.effective_user
        chat_id = str(update.effective_chat.id)

        # Импортируем здесь чтобы избежать циклических импортов
        from models import UserSubscription

        # Сохраняем/обновляем пользователя
        subscription = self.db_session.query(UserSubscription).filter_by(chat_id=chat_id).first()
        if not subscription:

            if not context.args:
                await update.message.reply_text("Использование: /start пароль")
                return

            password_attempt = ' '.join(context.args)

            if password_attempt != Config.USER_PASSWORD:
                await update.message.reply_text("❌ Неверный пароль!")
                return

            subscription = UserSubscription(
                chat_id=chat_id,
                username=user.username,
                first_name=user.first_name
            )
            self.db_session.add(subscription)
            self.db_session.commit()
            logger.info(f"Новый пользователь: {user.username} ({chat_id})")

        welcome_text = (
            "🚗 <b>Мониторинг цен</b>\n\n"
            "Я буду уведомлять вас о:\n"
            "• 📉 Снижениях цен на автомобили\n"
            "• 🆕 Появлении новых автомобилей\n\n"
            f"🕐 Время сбора новых авто: {Config.NEW_CARS_HOURS},"
            f" {_describe_interval(Config.NEW_CARS_INTERVAL_SECONDS)}\n"
            f"🕐 Время обновления авто: каждый день в {Config.UPDATE_CARS_HOURS}\n"
            f"🕐 Текущее время бота: {datetime.now(timezone)}\n\n"
            "📊 <b>Доступные команды:</b>\n"
            "/help - Помощь"
        )

        await update.message.reply_text(welcome_text, parse_mode='HTML')

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Помощь"""
        help_text = (
            "ℹ️ <b>Помощь по боту</b>\n\n"
            "<b>Команды:</b>\n"
            "/start - Запуск бота\n"
            "/help - Эта справка\n\n"
            "<b>Что отслеживаем:</b>\n"
            "• Снижения цен на автомобили\n"
            "• Появление новых автомобилей\n"
        )

        await update.message.reply_text(help_text, parse_mode='HTML')
