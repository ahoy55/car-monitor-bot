#!/usr/bin/env python3
"""
Скрипт для миграций базы данных
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / 'src'))

from sqlalchemy import create_engine, text
from models import Base
from config import Config
import logging

logger = logging.getLogger(__name__)


def run_migrations():
    """Запуск миграций базы данных"""

    engine = create_engine(f"sqlite:///{Config.DB_PATH}")

    # Проверяем существование таблицы миграций
    with engine.connect() as conn:
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS migrations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(255) NOT NULL,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
        except Exception as e:
            logger.error(f"Ошибка создания таблицы миграций: {e}")
            return

    logger.info("✅ Миграции проверены")


if __name__ == "__main__":
    run_migrations()
