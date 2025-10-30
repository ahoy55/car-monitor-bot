import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    IS_DEBUG = False

    # Sources
    SOURCES_PATH = os.getenv("SOURCES_PATH", "")

    # DB
    DB_HOST = os.getenv("DB_HOST", "")
    DB_PORT = os.getenv("DB_PORT", "")
    DB_NAME = os.getenv("DB_NAME", "")
    DB_USER = os.getenv("DB_USER", "")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DATABASE_URL = f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'

    # Scraper
    SCRAPE_INTERVAL = 15 if IS_DEBUG else int(os.getenv("SCRAPE_INTERVAL", 3600))
    SCRAPE_NEW_INTERVAL = 5 if IS_DEBUG else int(os.getenv("SCRAPE_NEW_INTERVAL", 600))

    # Telegram Bot
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")

    # Уведомления
    NOTIFY_PRICE_DROP_PERCENT = int(os.getenv("NOTIFY_PRICE_DROP_PERCENT", 5))
    NOTIFY_NEW_CARS = os.getenv("NOTIFY_NEW_CARS", "true").lower() == "true"

    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
