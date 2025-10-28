import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler

logger = logging.getLogger(__name__)

class TelegramBot:
    def __init__(self, db_session):
        self.db_session = db_session
        from config import Config
        self.application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()

        # Импортируем здесь чтобы избежать циклических импортов
        from bot.handlers import BotHandlers
        self.handlers = BotHandlers(db_session)

        self._setup_handlers()

    def _setup_handlers(self):
        """Настройка обработчиков"""
        # Команды
        self.application.add_handler(CommandHandler("start", self.handlers.start))
        self.application.add_handler(CommandHandler("settings", self.handlers.settings))
        self.application.add_handler(CommandHandler("stats", self.handlers.stats))
        self.application.add_handler(CommandHandler("help", self.handlers.help_command))

        # Inline кнопки
        self.application.add_handler(CallbackQueryHandler(self.handlers.handle_callback))

        # Сообщения
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self.handlers.handle_price_range
        ))

    async def start_bot(self):
        """Запуск бота"""
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()

        logger.info("✅ Telegram бот запущен")

    async def stop_bot(self):
        """Остановка бота"""
        await self.application.updater.stop()
        await self.application.stop()
        await self.application.shutdown()

        logger.info("✅ Telegram бот остановлен")

    def get_bot(self):
        """Получить экземпляр бота для уведомлений"""
        return self.application.bot
