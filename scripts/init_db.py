#!/usr/bin/env python3
"""
Скрипт инициализации базы данных
"""

import os
import sys
import logging
from pathlib import Path

# Добавляем путь к src для импорта модулей
sys.path.append(str(Path(__file__).parent.parent / 'src'))

from sqlalchemy import create_engine
from models import Base, UserSubscription
from config import Config

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def init_database():
    """Инициализация базы данных"""

    # Создаем директорию для базы данных, если её нет
    db_path = Path(Config.DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Инициализация базы данных: {db_path}")

    try:
        # Создаем движок и все таблицы
        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(engine)

        logger.info("✅ Таблицы успешно созданы:")
        for table in Base.metadata.tables.keys():
            logger.info(f"   - {table}")

        # Добавляем администратора, если указан chat_id
        if Config.ADMIN_CHAT_ID:
            from sqlalchemy.orm import sessionmaker
            Session = sessionmaker(bind=engine)
            session = Session()

            # Проверяем, существует ли уже администратор
            admin = session.query(UserSubscription).filter_by(chat_id=Config.ADMIN_CHAT_ID).first()

            if not admin:
                admin = UserSubscription(
                    chat_id=Config.ADMIN_CHAT_ID,
                    username="admin",
                    first_name="Administrator",
                    is_active=True,
                    notify_price_drops=True,
                    notify_new_cars=True,
                )
                session.add(admin)
                session.commit()
                logger.info(f"✅ Администратор добавлен: {Config.ADMIN_CHAT_ID}")
            else:
                logger.info("ℹ️ Администратор уже существует")

            session.close()

        logger.info("🎉 База данных успешно инициализирована!")

    except Exception as e:
        logger.error(f"❌ Ошибка инициализации базы данных: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("🚗 Инициализация базы данных мониторинга цен")
    print("=" * 60)

    init_database()
    print("🎉 Все готово! База данных успешно инициализирована.")
