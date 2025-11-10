import asyncio
import logging

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from database import Database
from models import Source
from source_manager import SourceManager
from config import Config
from bot.bot import TelegramBot

logger = logging.getLogger(__name__)
timezone = pytz.timezone('Europe/Moscow')

async def _keep_alive():
    """Бесконечный цикл для поддержания работы"""
    while True:
        await asyncio.sleep(1)


class ScheduleManager:

    def __init__(self):
        self.db = Database()
        self.db_session = self.db.Session
        self.bot = TelegramBot(self.db_session)
        self.scheduler = AsyncIOScheduler(
            timezone=timezone,
            job_defaults={
                'coalesce': True,
                'max_instances': 1,
                'misfire_grace_time': 300
            }
        )
        self.source_managers = self._get_source_managers()

    def _get_source_managers(self):
        session = self.db_session()
        source_list = session.query(Source).all()

        return list(
            map(
                lambda source: SourceManager(
                    source=source,
                    bot=self.bot.get_bot(),
                    db_session=self.db_session
                ),
                source_list
            )
        )

    async def process_cars_update(self):
        for source_manager in self.source_managers:
            await source_manager.process_updated_cars()

    async def process_cars_new(self):
        for source_manager in self.source_managers:
            await source_manager.process_new_cars()

    async def run(self):

        self.scheduler.add_job(
            id="update_cars",
            func=self.process_cars_update,
            trigger=CronTrigger(
                day_of_week=Config.WORK_DAYS,
                hour=Config.UPDATE_CARS_HOURS,
                minute=0,
                timezone=timezone
            ),
            misfire_grace_time=3600
        )

        self.scheduler.add_job(
            id="new_cars",
            func=self.process_cars_new,
            trigger=CronTrigger(
                day_of_week=Config.WORK_DAYS,
                hour=Config.NEW_CARS_HOURS,
                second=Config.NEW_CARS_INTERVAL_SECONDS,
                timezone=timezone
            ),
            misfire_grace_time=30
        )

        try:
            self.scheduler.start()

            if self.bot:
                await asyncio.gather(
                    self.bot.start_bot(),
                    _keep_alive()  # выносим цикл в отдельный метод
                )
            else:
                await _keep_alive()

        finally:
            if self.bot:
                await self.bot.stop_bot()
            self.scheduler.shutdown()
