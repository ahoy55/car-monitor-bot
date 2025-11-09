import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:

    # Debug
    IS_DEBUG = os.getenv("IS_DEBUG", "false").lower() == "true"

    # Sources
    SOURCES_PATH = os.getenv("SOURCES_PATH", "")

    # DB
    DATABASE_URL = os.getenv("DATABASE_URL", "")

    # Password
    USER_PASSWORD = os.getenv("USER_PASSWORD", "")

    # Scraper
    UPDATE_CARS_HOURS = int(os.getenv("UPDATE_CARS_HOURS", 10))
    NEW_CARS_HOUR_START = 0 if IS_DEBUG else int(os.getenv("NEW_CARS_HOUR_START", 10))
    NEW_CARS_HOUR_END = 23 if IS_DEBUG else int(os.getenv("NEW_CARS_HOUR_END", 18))
    NEW_CARS_INTERVAL_SECONDS = 5 if IS_DEBUG else int(os.getenv("NEW_CARS_INTERVAL_SECONDS", 59))

    # Telegram Bot
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")

    # Уведомления
    NOTIFY_PRICE_DROP_PERCENT = int(os.getenv("NOTIFY_PRICE_DROP_PERCENT", 5))
    NOTIFY_NEW_CARS = os.getenv("NOTIFY_NEW_CARS", "true").lower() == "true"

    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
