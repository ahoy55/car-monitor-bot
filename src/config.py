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
    UPDATE_CARS_HOURS = os.getenv("UPDATE_CARS_HOURS", "11,15")

    NEW_CARS_HOURS = "0-23" if IS_DEBUG else os.getenv("NEW_CARS_HOURS", "10-18")

    # поле second cron-триггера: "0" — раз в минуту, "*/5" — каждые 5 секунд
    NEW_CARS_INTERVAL_SECONDS = "*/5" if IS_DEBUG else os.getenv("NEW_CARS_INTERVAL_SECONDS", "0")

    WORK_DAYS = "mon-sun" if IS_DEBUG else os.getenv("WORK_DAYS", "mon-fri")

    # час (МСК), когда в общий чат группы уходят итоги дня
    DAILY_SUMMARY_HOUR = os.getenv("DAILY_SUMMARY_HOUR", "19")

    # Telegram Bot
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")
    CHANNEL_CHAT_ID = os.getenv("CHANNEL_CHAT_ID", 0)
    NEW_THREAD_ID = int(os.getenv("NEW_THREAD_ID", 0))
    PRICE_DROP_THREAD_ID = int(os.getenv("PRICE_DROP_THREAD_ID", 0))

    # Уведомления
    NOTIFY_PRICE_DROP_PERCENT = int(os.getenv("NOTIFY_PRICE_DROP_PERCENT", 5))
    NOTIFY_NEW_CARS = os.getenv("NOTIFY_NEW_CARS", "true").lower() == "true"
    # Типы техники, о которых уведомления приходят без звука: passenger,
    # cargo, trailer. Посты никуда не деваются — беззвучные не будят телефон,
    # но остаются в теме, в поиске и в итогах дня.
    SILENT_CAR_TYPES = {t.strip() for t in os.getenv("SILENT_CAR_TYPES", "passenger").split(",") if t.strip()}

    @classmethod
    def is_silent_type(cls, car_type) -> bool:
        # у машины без типа звук оставляем: непонятно, к какому разделу она относится
        return getattr(car_type, "value", car_type) in cls.SILENT_CAR_TYPES

    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
