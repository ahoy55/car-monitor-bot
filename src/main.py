import logging
import asyncio
import sys
import io
import os
from pathlib import Path
from typing import List

from changes import Changes
from models import Car

# Добавляем текущую директорию в Python path
sys.path.append(str(Path(__file__).parent))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from scraper import Scraper
from database import Database
from config import Config

# Пытаемся импортировать бота (если токен установлен)
try:
    from bot.bot import TelegramBot
    from bot.notifications import NotificationManager

    BOT_AVAILABLE = True
except ImportError as e:
    logging.warning(f"Bot modules not available: {e}")
    BOT_AVAILABLE = False

logger = logging.getLogger(__name__)

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


class CarMonitorApp:

    def __init__(self):
        self.db = Database()
        self.db_session = self.db.Session()
        self.scraper = Scraper()
        self.bot = None
        self.notification_manager = None

    async def initialize(self):
        """Инициализация приложения"""
        # Инициализация бота
        if BOT_AVAILABLE and Config.TELEGRAM_BOT_TOKEN:
            try:
                self.bot = TelegramBot(self.db_session)
                await self.bot.start_bot()
                self.notification_manager = NotificationManager(
                    self.bot.get_bot(),
                    self.db_session
                )
                logger.info("✅ Telegram bot initialized")
            except Exception as e:
                logger.error(f"❌ Failed to initialize bot: {e}")
        else:
            logger.info("ℹ️ Telegram bot disabled (no token)")
            logger.info(BOT_AVAILABLE)
            logger.info(Config.TELEGRAM_BOT_TOKEN)

    async def notify_changes(self, changes: List[Changes]):
        for change in changes:
            car_data = change.car_data
            old_price = change.old_price
            car = Car.from_dict(car_data)
            await self.notification_manager.notify_price_drop(car, old_price)

    async def scrape_pages_and_save(self):
        """Основная функция сбора данных с уведомлениями"""
        logger.info("Запуск сбора данных постранично...")

        try:
            car_types = [2, 4]

            for car_type in car_types:
                cars_data = self.scraper.scrape_all_pages(max_pages=25, car_type=car_type)
                await self.db.save_cars(cars_data, self.notify_changes)

            # logger.info(f"✅ Обновление данных завершено. Обработано: {len(cars_data)} автомобилей")

        except Exception as e:
            logger.error(f"❌ Ошибка в основном процессе: {e}")

    async def notify_new(self, cars_data: List):
        for car_data in cars_data:
            car = Car.from_dict(car_data)
            await self.notification_manager.notify_new_car(car)

    async def scrape_new_and_save(self):
        """Основная функция сбора данных с уведомлениями"""
        logger.info("Запуск сбора данных со страницы новых...")

        try:
            car_types = [2, 4]

            for car_type in car_types:
                cars_data = self.scraper.scrape_page_new(car_type=car_type)
                await self.db.check_existing_cars(cars_data, self.notify_new)

            logger.info(f"✅ Сбор новых машин завершен")

        except Exception as e:
            logger.error(f"❌ Ошибка в основном процессе: {e}")

    async def run(self):
        """Запуск приложения"""
        await self.initialize()

        # Запускаем сразу
        await self.scrape_pages_and_save()
        await self.scrape_new_and_save()

        # Планировщик
        new_scheduler = AsyncIOScheduler()
        pages_scheduler = AsyncIOScheduler()

        new_scheduler.add_job(
            self.scrape_new_and_save,
            'interval',
            seconds=Config.SCRAPE_NEW_INTERVAL
        )

        pages_scheduler.add_job(
            self.scrape_pages_and_save,
            'interval',
            seconds=Config.SCRAPE_INTERVAL
        )

        try:
            new_scheduler.start()
            pages_scheduler.start()
            logger.info(f"🚗 Мониторинг запущен. Интервал: для обновления {Config.SCRAPE_INTERVAL} секунд, "
                        f"для новых {Config.SCRAPE_NEW_INTERVAL}")

            # Бесконечный цикл для работы бота
            while True:
                await asyncio.sleep(1)

        except KeyboardInterrupt:
            logger.info("Приложение остановлено")
        finally:
            if self.bot:
                await self.bot.stop_bot()
            new_scheduler.shutdown()
            pages_scheduler.shutdown()


async def main():
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/monitor.log'),
            logging.StreamHandler()
        ]
    )

    app = CarMonitorApp()
    await app.run()


if __name__ == "__main__":
    asyncio.run(main())
