import logging
from typing import List

from bot.notifications import NotificationManager
from models import Source, Car, CarType
from base_source_processor import BaseSourceProcessor
from source_processor_1 import SourceProcessor1

logger = logging.getLogger(__name__)


class Change:

    def __init__(self, car: Car, old_price=""):
        self.car = car
        self.old_price = old_price  # 0 if this is new car


def _is_price_drop(old_price: str, new_price: str) -> bool:
    """Проверяет снизилась ли цена"""
    try:
        old_clean = int(''.join(filter(str.isdigit, old_price)))
        new_clean = int(''.join(filter(str.isdigit, new_price)))
        return old_clean > new_clean
    except (ValueError, AttributeError):
        return False


def get_source_processor(car_types: List[CarType], source: Source) -> BaseSourceProcessor:
    if source.id == 1:
        return SourceProcessor1(car_types, source)
    elif source.id == 2:
        pass


class SourceManager:

    def __init__(self, source, bot, db_session):
        self.db_session = db_session
        self.car_types = [CarType.PASSENGER, CarType.CARGO]
        self.notification_manager = NotificationManager(bot, db_session)
        self.source_processor = get_source_processor(self.car_types, source)
        self.source = source

    async def process_new_cars(self):
        logger.info(f"Поиск новых машин из источника: {self.source.name}")
        session = self.db_session()
        car_list = self.source_processor.scrape_new_cars()
        new_car_list = []
        try:
            for car in car_list:
                is_car_exists = session.query(Car).filter_by(car_id=car.car_id).first() is not None
                if not is_car_exists:
                    car.source = self.source
                    new_car_list.append(car)
                    session.add(car)
                session.commit()

            if new_car_list:
                await self.notify_new(new_car_list)

        except Exception as e:
            session.rollback()
            logger.error(f"❌ Ошибка: {e}")
        finally:
            session.close()

    async def process_updated_cars(self):
        logger.info(f"Обновление цен на машины из источника: {self.source.name}")
        session = self.db_session()
        car_list = self.source_processor.scrape_updated_cars()
        print(car_list)
        changes = []
        new_car_list = []
        try:
            for car in car_list:
                existing_car = session.query(Car).filter_by(car_id=car.car_id).first()
                if existing_car:
                    new_price = car.price
                    old_price = existing_car.price

                    if old_price != new_price:
                        print(f'{old_price} {new_price}')

                        if _is_price_drop(old_price, new_price):
                            changes.append(Change(car, old_price))

                        existing_car.price = new_price
                        existing_car.monthly_payment = car.monthly_payment
                        existing_car.city = car.city
                        existing_car.mileage = car.mileage
                        existing_car.year = car.year
                        session.commit()
                else:
                    car.source = self.source
                    new_car_list.append(car)
                    session.add(car)

            if changes:
                await self.notify_changes(changes)

            if new_car_list:
                await self.notify_new(new_car_list)

        except Exception as e:
            session.rollback()
            logger.error(f"❌ Ошибка: {e}")
        finally:
            session.close()

    async def notify_changes(self, changes: List[Change]):
        for change in changes:
            await self.notification_manager.notify_price_drop(change.car, change.old_price)

    async def notify_new(self, cars: List[Car]):
        for car in cars:
            await self.notification_manager.notify_new_car(car)
