import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from database import Database
from models import Source
from source_manager import SourceManager

logger = logging.getLogger(__name__)


class ScheduleManager:

    def __init__(self, bot):
        self.db = Database()
        self.db_session = self.db.Session
        self.bot = bot
        self.update_cars_scheduler = AsyncIOScheduler()
        self.new_cars_scheduler = AsyncIOScheduler()
        self.source_managers = self._get_source_managers()

    def _get_source_managers(self):
        session = self.db_session()
        source_list = session.query(Source).all()

        return list(
            map(
                lambda source: SourceManager(
                    source=source,
                    bot=self.bot,
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

        """Запускает планировщик на 00:00 для обновления цен на машины"""
        self.update_cars_scheduler.add_job(
            func=self.process_cars_update,
            trigger=CronTrigger(hour='8-23', second='*/5')
            # trigger=CronTrigger(hour=0, minute=0),
        )

        # """Запускает планировщик на с 8:00 до 19:59 для поиска новых машин"""
        self.new_cars_scheduler.add_job(
            func=self.process_cars_new,
            # trigger=CronTrigger(hour='0-23', second='*/5')
            trigger=CronTrigger(second='*/5')
        )
        #
        try:
            self.update_cars_scheduler.start()
            self.new_cars_scheduler.start()

            while True:
                await asyncio.sleep(1)

        finally:
            if self.bot:
                await self.bot.stop_bot()
            self.update_cars_scheduler.shutdown()
            self.new_cars_scheduler.shutdown()
