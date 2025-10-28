from typing import Callable, List, Any, Coroutine

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, Car, PriceHistory
from config import Config
import logging

from src.changes import Changes

logger = logging.getLogger(__name__)


def _is_price_drop(old_price: str, new_price: str) -> bool:
    """Проверяет снизилась ли цена"""
    try:
        old_clean = int(''.join(filter(str.isdigit, old_price)))
        new_clean = int(''.join(filter(str.isdigit, new_price)))
        return old_clean > new_clean
    except (ValueError, AttributeError):
        return False


class Database:
    def __init__(self):
        self.engine = create_engine(
            Config.DATABASE_URL,
            # Дополнительные настройки для стабильности
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            echo=Config.IS_DEBUG  # Показывает SQL запросы в консоли при DEBUG
        )

        # Тестируем подключение
        with self.engine.connect():
            logging.info("✅ Successfully connected to PostgreSQL")

        # Создаем таблицы
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

        logging.info("✅ Database tables created successfully")

        self.clear_test_data()
        logging.info("✅ Database tables cleared successfully")

    async def save_cars(self, cars_data, callback: Callable[[list], Coroutine[Any, Any, None]]):
        session = self.Session()
        new_cars = []  # новые автомобили
        price_drops = []  # снижения цен
        updated_cars_count = 0
        new_cars_count = 0

        try:
            # Получаем все существующие автомобили для быстрого поиска
            existing_cars = {car.car_id: car for car in session.query(Car).all()}

            for car_data in cars_data:
                car_id = car_data['id']

                if car_id in existing_cars:
                    # Обновляем существующий автомобиль
                    existing_car = existing_cars[car_id]
                    new_price = car_data.get('price', '')
                    old_price = existing_car.price

                    # Проверяем любые изменения
                    if old_price != new_price:

                        # Сохраняем историю цен если цена изменилась
                        if old_price != new_price:
                            price_history = PriceHistory(
                                car_id=car_id,
                                price=new_price,
                                monthly_payment=car_data.get('monthly_payment')
                            )
                            session.add(price_history)

                            # Проверяем снижение цены
                            if _is_price_drop(old_price, new_price):
                                price_drops.append(Changes(car_data, old_price))

                        # Обновляем данные автомобиля
                        existing_car.price = new_price
                        existing_car.monthly_payment = car_data.get('monthly_payment')
                        existing_car.city = car_data.get('city')
                        existing_car.mileage = car_data.get('mileage')
                        existing_car.year = car_data.get('year')

                        updated_cars_count += 1

                else:
                    # Добавляем новый автомобиль
                    car = Car.from_dict(car_data)
                    session.add(car)

                    # Сохраняем первоначальную цену в историю
                    price_history = PriceHistory(
                        car_id=car_id,
                        price=car_data.get('price'),
                        monthly_payment=car_data.get('monthly_payment')
                    )
                    session.add(price_history)
                    new_cars_count += 1

            session.commit()
            logger.info(f"✅ Сохранено: {new_cars_count} новых, {updated_cars_count} обновленных автомобилей")

        except Exception as e:
            session.rollback()
            logger.error(f"❌ Ошибка сохранения в БД: {e}")
        finally:
            session.close()

        # Уведомления
        if price_drops:
            await callback(price_drops)

    async def check_existing_cars(self, cars_data, callback: Callable[[list], Coroutine[Any, Any, None]]):
        session = self.Session()
        new_cars = []

        try:
            for car_data in cars_data:
                # Проверяем существующую запись
                existing_car = session.query(Car).filter_by(car_id=car_data['id']).first()
                if not existing_car:
                    car = Car.from_dict(car_data)
                    session.add(car)
                    new_cars.append(car_data)

            logger.info(f"Добавлено {len(new_cars)} новых автомобилей")
            session.commit()

        except Exception as e:
            session.rollback()
            logger.error(f"❌ Ошибка сохранения в БД: {e}")
        finally:
            session.close()

        if len(new_cars) > 0:
            await callback(new_cars)

    def get_stats(self):
        """Получить статистику"""
        session = self.Session()
        try:
            total_cars = session.query(Car).count()
            total_price_history = session.query(PriceHistory).count()
            return {
                "total_cars": total_cars,
                "total_price_history": total_price_history
            }
        finally:
            session.close()

    def clear_test_data(self):
        """Очистка тестовых данных (только для debug режима)"""
        if not Config.IS_DEBUG:
            return

        session = self.Session()
        try:
            # Для PostgreSQL лучше использовать truncate для сброса sequence
            session.execute("TRUNCATE TABLE price_history RESTART IDENTITY CASCADE;")
            session.execute("TRUNCATE TABLE cars RESTART IDENTITY CASCADE;")
            session.commit()
            logging.info("Test data cleared")
        except Exception as e:
            session.rollback()
            logging.error(f"Error clearing test data: {e}")
        finally:
            session.close()
