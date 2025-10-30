import asyncio
import logging
import os
import sys
import logging_helper

from pathlib import Path
from schedule_manager import ScheduleManager
from bot.bot import TelegramBot
from config import Config
from database import Database

# Добавляем текущую директорию в Python path
sys.path.append(str(Path(__file__).parent))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

logger = logging.getLogger(__name__)


class CarMonitorApp:

    def __init__(self):
        self.db = Database()
        self.db_session = self.db.Session

    async def run(self):
        logging_helper.initialize()
        schedule_manager = ScheduleManager()
        await schedule_manager.run()


async def main():
    app = CarMonitorApp()
    await app.run()

if __name__ == "__main__":
    asyncio.run(main())
