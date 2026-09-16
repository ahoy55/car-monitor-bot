#!/usr/bin/env python3
import json
import logging
import sys
import time

from pathlib import Path

from psycopg2 import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, text

sys.path.append(str(Path(__file__).parent.parent / 'src'))

from models import Base, UserSubscription, Source
from config import Config

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_from_file(json_file_path: str):
    """Загрузка данных из JSON файла"""
    try:
        with open(json_file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
        return data
    except Exception as e:
        print(f"❌ Ошибка загрузки JSON файла: {e}")
        return False


def wait_for_postgres(max_retries=30, delay=2):
    """Ждем пока PostgreSQL не станет доступен"""
    from config import Config

    for i in range(0, max_retries):
        try:
            logger.info(f"🔄 Попытка подключения к БД ({i + 1}/{max_retries})...")
            engine = create_engine(Config.DATABASE_URL)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("✅ База данных доступна!")
            return True
        except OperationalError as e:
            logger.warning(f"⏳ БД еще не готова: {e}")
            if i < max_retries - 1:
                time.sleep(delay)
            else:
                logger.error("❌ Не удалось подключиться к БД после всех попыток")
                return False


class DbInitializer():

    def __init__(self):
        self.engine = create_engine(
            Config.DATABASE_URL,
            # Дополнительные настройки для стабильности
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            echo=True  # Показывает SQL запросы в консоли при DEBUG
        )
        session_maker = sessionmaker(bind=self.engine)
        self.session = session_maker()

    def init_database(self):
        """Инициализация базы данных"""

        db_path = Config.DATABASE_URL
        logger.info(f"Инициализация базы данных: {db_path}")
        try:

            # Создаем движок и все таблицы
            Base.metadata.create_all(self.engine)

            logger.info("✅ Таблицы успешно созданы:")
            for table in Base.metadata.tables.keys():
                logger.info(f"   - {table}")

            self.add_missing_columns()

            self.add_telegram_admin()
            self.populate_sources()
            logger.info("🎉 База данных успешно инициализирована!")

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации базы данных: {e}")
            sys.exit(1)

    def add_missing_columns(self):
        """create_all создаёт только отсутствующие таблицы, новые колонки
        в уже существующие не добавляет — дописываем их сами, идемпотентно."""
        with self.engine.begin() as conn:
            conn.execute(text("ALTER TABLE cars ADD COLUMN IF NOT EXISTS brand VARCHAR(100)"))
            conn.execute(text(
                "ALTER TABLE price_history ADD COLUMN IF NOT EXISTS is_reference BOOLEAN NOT NULL DEFAULT FALSE"))
        logger.info("✅ Колонки таблиц cars и price_history проверены")

    def add_telegram_admin(self):
        # Добавляем администратора, если указан chat_id
        if Config.ADMIN_CHAT_ID:
            admin = self.session.query(UserSubscription).filter_by(chat_id=Config.ADMIN_CHAT_ID).first()

            if not admin:
                admin = UserSubscription(
                    chat_id=Config.ADMIN_CHAT_ID,
                    username="admin",
                    first_name="Administrator",
                    is_active=True,
                    notify_price_drops=True,
                    notify_new_cars=True,
                )
                self.session.add(admin)
                self.session.commit()
                logger.info(f"✅ Администратор добавлен: {Config.ADMIN_CHAT_ID}")
            else:
                logger.info("ℹ️ Администратор уже существует")

            self.session.close()

    def populate_sources(self):
        json_file_path = Config.SOURCES_PATH
        logger.info(f'ℹ️ Заполнение данные источников из файла {json_file_path}')
        source_data_list = load_from_file(json_file_path)
        source_list = []
        for source_data in source_data_list:
            source_id = source_data['source_id']
            source = self.session.query(Source).filter_by(source_id=source_id).first()
            if source:
                # Файл — источник истины: иначе смена template_url требовала бы
                # ручного UPDATE на проде, файл и база расходились бы молча
                changed = [
                    field for field, value in (
                        ('name', source_data['name']),
                        ('base_url', source_data['base_url']),
                        ('template_url', source_data['template_url']),
                    ) if getattr(source, field) != value
                ]
                for field in changed:
                    setattr(source, field, source_data[field])

                if changed:
                    logger.info(f'♻️  Источник {source.name} обновлён: {", ".join(changed)}')
                else:
                    logger.info(f'✅  Источник {source.name} уже добавлен')
            else:
                source_list.append(
                    Source(
                        source_id=source_id,
                        name=source_data['name'],
                        base_url=source_data['base_url'],
                        template_url=source_data['template_url']
                    )
                )

        self.session.bulk_save_objects(source_list)
        self.session.commit()
        logger.info(f"✅  Добавлено {len(source_list)} источников: {', '.join(map(lambda i: i.name, source_list))}.")


if __name__ == "__main__":
    print("🚗 Инициализация базы данных мониторинга цен")
    print("=" * 60)

    initializer = DbInitializer()
    initializer.init_database()
    print("🎉 Все готово! База данных успешно инициализирована.")
