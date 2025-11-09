import logging
from datetime import datetime

import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler

from config import Config

logger = logging.getLogger(__name__)
timezone = pytz.timezone('Europe/Moscow')


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
            f"🕐 Время сбора новых авто: {Config.NEW_CARS_HOURS}"
            f" с интервалом {Config.NEW_CARS_INTERVAL_SECONDS}\n"
            f"🕐 Время обновления авто: каждый день в {Config.UPDATE_CARS_HOURS}\n"
            f"🕐 Текущее время бота: {datetime.now(timezone)}\n\n"
            "📊 <b>Доступные команды:</b>\n"
            "/settings - Настройки уведомлений\n"
            "/help - Помощь"
        )

        await update.message.reply_text(welcome_text, parse_mode='HTML')

    async def settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Настройки уведомлений"""
        chat_id = str(update.effective_chat.id)

        from models import UserSubscription
        subscription = self.db_session.query(UserSubscription).filter_by(chat_id=chat_id).first()

        if not subscription:
            await update.message.reply_text("Сначала запустите бота командой /start")
            return

        keyboard = [
            [InlineKeyboardButton(
                f"🔔 Уведомления о снижении цен: {'ВКЛ' if subscription.notify_price_drops else 'ВЫКЛ'}",
                callback_data="toggle_price_drops"
            )],
            [InlineKeyboardButton(
                f"🆕 Уведомления о новых авто: {'ВКЛ' if subscription.notify_new_cars else 'ВЫКЛ'}",
                callback_data="toggle_new_cars"
            )],
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        status_text = (
            f"⚙️ <b>Настройки уведомлений</b>\n\n"
            f"🔔 Снижение цен: {'✅ ВКЛ' if subscription.notify_price_drops else '❌ ВЫКЛ'}\n"
            f"🆕 Новые авто: {'✅ ВКЛ' if subscription.notify_new_cars else '❌ ВЫКЛ'}\n"
        )

        await update.message.reply_text(status_text, parse_mode='HTML', reply_markup=reply_markup)

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        chat_id = str(query.message.chat.id)

        from models import UserSubscription
        subscription = self.db_session.query(UserSubscription).filter_by(chat_id=chat_id).first()

        if not subscription:
            await query.edit_message_text("Сначала запустите бота командой /start")
            return

        if query.data == "toggle_price_drops":
            subscription.notify_price_drops = not subscription.notify_price_drops
            self.db_session.commit()

        elif query.data == "toggle_new_cars":
            subscription.notify_new_cars = not subscription.notify_new_cars
            self.db_session.commit()

        # Обнови сообщение после любых изменений
        await self._update_settings_message(query, subscription)

    async def _update_settings_message(self, query, subscription):
        """Обновляет сообщение с настройками"""
        keyboard = [
            [InlineKeyboardButton(
                f"🔔 Уведомления о снижении цен: {'ВКЛ' if subscription.notify_price_drops else 'ВЫКЛ'}",
                callback_data="toggle_price_drops"
            )],
            [InlineKeyboardButton(
                f"🆕 Уведомления о новых авто: {'ВКЛ' if subscription.notify_new_cars else 'ВЫКЛ'}",
                callback_data="toggle_new_cars"
            )],
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        status_text = (
            f"⚙️ <b>Настройки уведомлений</b>\n\n"
            f"🔔 Снижение цен: {'✅ ВКЛ' if subscription.notify_price_drops else '❌ ВЫКЛ'}\n"
            f"🆕 Новые авто: {'✅ ВКЛ' if subscription.notify_new_cars else '❌ ВЫКЛ'}\n"
        )

        await query.edit_message_text(status_text, parse_mode='HTML', reply_markup=reply_markup)

    async def handle_price_range(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик установки ценового диапазона"""
        try:
            min_price, max_price = map(int, update.message.text.split())
            chat_id = str(update.effective_chat.id)

            from models import UserSubscription
            subscription = self.db_session.query(UserSubscription).filter_by(chat_id=chat_id).first()
            subscription.min_price = min_price
            subscription.max_price = max_price
            self.db_session.commit()

            await update.message.reply_text(
                f"✅ Диапазон цен установлен: {min_price:,} - {max_price:,} ₽"
            )

        except ValueError:
            await update.message.reply_text("❌ Неверный формат. Используйте: <code>100000 5000000</code>",
                                            parse_mode='HTML')

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Статистика"""
        from models import Car
        total_cars = self.db_session.query(Car).count()

        stats_text = (
            "📊 <b>Статистика мониторинга</b>\n\n"
            f"🚗 Всего автомобилей в базе: {total_cars}\n"
            f"⏰ Следующее обновление: через 1 час\n"
        )

        await update.message.reply_text(stats_text, parse_mode='HTML')

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Помощь"""
        help_text = (
            "ℹ️ <b>Помощь по боту</b>\n\n"
            "<b>Команды:</b>\n"
            "/start - Запуск бота\n"
            "/settings - Настройки уведомлений\n"
            "/help - Эта справка\n\n"
            "<b>Что отслеживаем:</b>\n"
            "• Снижения цен на автомобили\n"
            "• Появление новых автомобилей\n"
        )

        await update.message.reply_text(help_text, parse_mode='HTML')
