import logging
from telegram.ext import Application, CommandHandler

from .handlers import BotHandlers
from config import Config

logger = logging.getLogger(__name__)


class TelegramBot:

    def __init__(self, db_session):
        self.db_session = db_session
        self.application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
        self.handlers = BotHandlers(db_session)
        self._setup_handlers()

    async def initialize(self):
        if Config.TELEGRAM_BOT_TOKEN:
            try:
                await self.start_bot()
            except Exception as e:
                logger.error(f"❌ Failed to initialize bot: {e}")
        else:
            logger.info("ℹ️ Telegram bot disabled (no token)")

    def _setup_handlers(self):
        """Настройка обработчиков"""
        # Уведомления уходят в канал, а не подписчикам, поэтому команд
        # настройки подписки нет — только вход по паролю и справка
        self.application.add_handler(CommandHandler("start", self.handlers.start))
        self.application.add_handler(CommandHandler("help", self.handlers.help_command))

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
