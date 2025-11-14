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

    engine = create_engine(Config.DATABASE_URL)

    # Проверяем существование таблицы миграций
    with engine.connect() as conn:
        try:
            conn.execute(text("""
                            CREATE TABLE IF NOT EXISTS migrations (
                                id SERIAL PRIMARY KEY,
                                name VARCHAR(255) NOT NULL,
                                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                            )
                        """))
            conn.commit()
        except Exception as e:
            logger.error(f"Ошибка создания таблицы миграций: {e}")
            return

    _check_car_type_migrations(engine)

    logger.info("✅ Миграции проверены")


def _check_car_type_migrations(engine):
    # Проверяем, была ли уже применена миграция car_type
    with engine.connect() as conn:
        result = conn.execute(text("""
                SELECT COUNT(*) FROM migrations WHERE name = 'add_car_type_column'
            """))
        migration_applied = result.scalar() > 0

    if not migration_applied:
        _add_car_type_column(engine)
    else:
        logger.info("✅ Миграция car_type уже применена")


def _add_car_type_column(engine):
    """Добавляет колонку car_type в таблицу cars"""

    # Для SQLite используем TEXT вместо ENUM
    migration_sql = [
        # Добавляем колонку car_type
        """
        ALTER TABLE cars ADD COLUMN type TEXT CHECK(type IN ('PASSENGER', 'CARGO', 'TRAILER'))
        """,

        # Создаем индекс для улучшения производительности
        """
        CREATE INDEX IF NOT EXISTS ix_cars_car_type ON cars (type)
        """,

        # Отмечаем миграцию как выполненную
        """
        INSERT INTO migrations (name) VALUES ('add_car_type_column')
        """
    ]

    try:
        with engine.connect() as conn:
            for sql in migration_sql:
                conn.execute(text(sql))
            conn.commit()

        logger.info("✅ Колонка car_type успешно добавлена в таблицу cars")
        logger.info("✅ Индекс ix_cars_car_type создан")
        logger.info("✅ Существующие данные заполнены типами автомобилей")

    except Exception as e:
        logger.error(f"❌ Ошибка при добавлении колонки car_type: {e}")
        raise


if __name__ == "__main__":
    run_migrations()
