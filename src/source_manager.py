import asyncio
import logging
from typing import Dict, Iterable, List

from bot.notifications import NotificationManager
from models import Source, Car, CarType
from base_source_processor import BaseSourceProcessor
from source_processor_1 import SourceProcessor1
from source_processor_2 import SourceProcessor2
from bot.templates import PriceDrop

logger = logging.getLogger(__name__)

EXISTING_CARS_CHUNK = 1000


def _is_price_drop(old_price: str, new_price: str) -> bool:
    """Проверяет снизилась ли цена"""
    try:
        old_clean = int(''.join(filter(str.isdigit, old_price)))
        new_clean = int(''.join(filter(str.isdigit, new_price)))
        return old_clean > new_clean
    except (ValueError, AttributeError):
        return False


def _find_existing_cars(session, car_ids: Iterable[str]) -> Dict[str, Car]:
    """Одним запросом на пачку вместо запроса на каждую машину: при полном
    обходе машин тысячи, и поштучные запросы надолго занимали цикл событий."""
    car_ids = list(car_ids)
    existing = {}
    for start in range(0, len(car_ids), EXISTING_CARS_CHUNK):
        chunk = car_ids[start:start + EXISTING_CARS_CHUNK]
        for car in session.query(Car).filter(Car.car_id.in_(chunk)):
            existing[car.car_id] = car
    return existing


def get_source_processor(car_types: List[CarType], source: Source) -> BaseSourceProcessor:
    if source.id == 1:
        return SourceProcessor1(car_types, source)
    elif source.id == 2:
        return SourceProcessor2(car_types, source)


class SourceManager:

    def __init__(self, source, bot, db_session):
        self.db_session = db_session
        self.car_types = [CarType.PASSENGER, CarType.CARGO, CarType.TRAILER]
        self.notification_manager = NotificationManager(bot, db_session)
        self.source_processor = get_source_processor(self.car_types, source)
        self.source = source
        # Сбор идёт в отдельном потоке, поэтому поиск новых и обновление цен
        # могут запуститься одновременно. У процессора одна HTTP-сессия,
        # а вставка одних и тех же машин упала бы на уникальном car_id.
        self.lock = asyncio.Lock()

    async def process_new_cars(self):
        async with self.lock:
            logger.info(f"Поиск новых машин из источника: {self.source.name}")
            try:
                car_list = await asyncio.to_thread(self.source_processor.scrape_new_cars)
            except Exception as e:
                logger.error(f"❌ Ошибка сбора: {e}")
                return

            if car_list is None:
                logger.error("❌ Ошибка: scrape_new_cars() вернул None")
                return

            session = self.db_session()
            try:
                source = session.query(Source).get(self.source.id)
                known_cars = _find_existing_cars(session, (car.car_id for car in car_list))
                new_car_list = []

                for car in car_list:
                    # одна и та же машина может встретиться в выдаче дважды
                    if car.car_id in known_cars:
                        continue
                    car.source = source
                    new_car_list.append(car)
                    known_cars[car.car_id] = car
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
        async with self.lock:
            logger.info(f"Обновление цен на машины из источника: {self.source.name}")
            try:
                car_list = await asyncio.to_thread(self.source_processor.scrape_updated_cars)
            except Exception as e:
                logger.error(f"❌ Ошибка сбора: {e}")
                return

            if car_list is None:
                logger.error("❌ Ошибка: scrape_updated_cars() вернул None")
                return

            session = self.db_session()
            try:
                source = session.query(Source).get(self.source.id)
                known_cars = _find_existing_cars(session, (car.car_id for car in car_list))
                price_drops = []

                for car in car_list:
                    existing_car = known_cars.get(car.car_id)
                    if existing_car:
                        new_price = car.price
                        old_price = existing_car.price

                        if old_price != new_price:
                            print(f'{old_price} {new_price}')

                            existing_car.price = new_price
                            existing_car.monthly_payment = car.monthly_payment
                            existing_car.city = car.city
                            existing_car.mileage = car.mileage
                            existing_car.year = car.year

                            if _is_price_drop(old_price, new_price):
                                price_drops.append(PriceDrop(existing_car, old_price))

                    else:
                        car.source = source
                        known_cars[car.car_id] = car
                        session.add(car)

                session.commit()

                if price_drops:
                    await self.notify_changes(price_drops)

            except Exception as e:
                session.rollback()
                logger.error(f"❌ Ошибка: {e}")
            finally:
                session.close()

    async def notify_changes(self, price_drops: List[PriceDrop]):
        await self.notification_manager.notify_price_drop(price_drops)

    async def notify_new(self, cars: List[Car]):
        await self.notification_manager.notify_new_car(cars)
