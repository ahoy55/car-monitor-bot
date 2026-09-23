import asyncio
import logging
from typing import Dict, Iterable, List, Optional

from bot.notifications import NotificationManager
from models import Source, Car, CarType, PriceHistory
from base_source_processor import BaseSourceProcessor
from source_processor_1 import SourceProcessor1
from source_processor_2 import SourceProcessor2
from source_processor_3 import SourceProcessor3
from bot.templates import PriceDrop, get_drop_percent
from config import Config
from source_health import SourceHealth

logger = logging.getLogger(__name__)

EXISTING_CARS_CHUNK = 1000

# Поиск новых идёт раз в минуту — разовый сетевой сбой не повод будить
# админа, сообщаем после нескольких неудач подряд. Обновление цен идёт
# дважды в день, поэтому о нём — сразу.
NEW_CARS_FAILURES_TO_ALERT = 3
UPDATED_CARS_FAILURES_TO_ALERT = 1
# Обход, оборвавшийся на полпути, не падает, а просто приносит меньше машин
UPDATED_CARS_MIN_SHARE = 0.5
ERROR_TEXT_LIMIT = 300


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


def _short_error(error: Exception) -> str:
    """Суть ошибки для алерта. Текст ошибки SQLAlchemy содержит весь SQL
    с параметрами — тысячи символов, и Telegram такой алерт не принимает."""
    original = getattr(error, 'orig', None) or error
    text = ' '.join(str(original).split())
    return text[:ERROR_TEXT_LIMIT] + ('…' if len(text) > ERROR_TEXT_LIMIT else '')


def _load_price_histories(session, car_ids: Iterable[str]) -> Dict[str, List[PriceHistory]]:
    """История цен по машинам, от старых записей к новым."""
    car_ids = list(car_ids)
    histories = {}
    for start in range(0, len(car_ids), EXISTING_CARS_CHUNK):
        chunk = car_ids[start:start + EXISTING_CARS_CHUNK]
        rows = (session.query(PriceHistory)
                .filter(PriceHistory.car_id.in_(chunk))
                .order_by(PriceHistory.created_at, PriceHistory.id))
        for row in rows:
            histories.setdefault(row.car_id, []).append(row)
    return histories


def _starting_price_entry(car: Car) -> PriceHistory:
    return PriceHistory(car_id=car.car_id, price=car.price, monthly_payment=car.monthly_payment, is_reference=True)


def _has_price(price: Optional[str]) -> bool:
    # у лотов внешних торгов вместо суммы "Аукцион"
    return any(c.isdigit() for c in price or "")


def _count_drops(history: List[PriceHistory]) -> int:
    return sum(1 for previous, current in zip(history, history[1:]) if _is_price_drop(previous.price, current.price))


def get_source_processor(car_types: List[CarType], source: Source) -> BaseSourceProcessor:
    if source.id == 1:
        return SourceProcessor1(car_types, source)
    elif source.id == 2:
        return SourceProcessor2(car_types, source)
    elif source.id == 3:
        return SourceProcessor3(car_types, source)


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
        self.new_cars_health = SourceHealth(source.name, "поиск новых машин", NEW_CARS_FAILURES_TO_ALERT)
        self.updated_cars_health = SourceHealth(source.name, "обновление цен", UPDATED_CARS_FAILURES_TO_ALERT)
        self.last_updated_count = None
        # у каждого источника свои темы; без них — общие из окружения
        self.new_thread_id = source.new_thread_id or Config.NEW_THREAD_ID
        self.price_drop_thread_id = source.price_drop_thread_id or Config.PRICE_DROP_THREAD_ID

    async def process_new_cars(self):
        if self.lock.locked():
            # Источник занят другим сбором — обычно полным обходом, иногда
            # поиском новых, запущенным при старте. Не ждём его: иначе поиск
            # новых по всем источникам стоял бы на паузе минут двадцать. Новые
            # машины, найденные обходом, он объявит сам — см. process_updated_cars.
            logger.info(f"{self.source.name}: источник занят другим сбором, поиск новых пропущен")
            return

        async with self.lock:
            logger.info(f"Поиск новых машин из источника: {self.source.name}")
            errors_before = self.source_processor.error_count
            try:
                car_list = await asyncio.to_thread(self.source_processor.scrape_new_cars)
            except Exception as e:
                logger.error(f"❌ Ошибка сбора: {e}")
                await self._report(self.new_cars_health, f"сбор упал с ошибкой: {_short_error(e)}")
                return

            problem = self._check_scraped(car_list, errors_before)

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
                    session.add(_starting_price_entry(car))
                session.commit()

                if new_car_list:
                    await self._announce_new_cars(session, new_car_list)

            except Exception as e:
                session.rollback()
                logger.error(f"❌ Ошибка: {e}")
                problem = problem or f"ошибка сохранения: {_short_error(e)}"
            finally:
                session.close()

            await self._report(self.new_cars_health, problem)

    async def process_updated_cars(self):
        async with self.lock:
            logger.info(f"Обновление цен на машины из источника: {self.source.name}")
            errors_before = self.source_processor.error_count
            try:
                car_list = await asyncio.to_thread(self.source_processor.scrape_updated_cars)
            except Exception as e:
                logger.error(f"❌ Ошибка сбора: {e}")
                await self._report(self.updated_cars_health, f"сбор упал с ошибкой: {_short_error(e)}")
                return

            problem = self._check_scraped(car_list, errors_before, self.last_updated_count)
            if not problem:
                self.last_updated_count = len(car_list)

            session = self.db_session()
            try:
                source = session.query(Source).get(self.source.id)
                # Первый обход нового источника незнаком со всеми его машинами —
                # их добавляем молча, иначе в канал ушли бы тысячи "новых".
                source_was_filled = session.query(Car.id).filter(Car.source_id == self.source.id).first() is not None
                known_cars = _find_existing_cars(session, (car.car_id for car in car_list))
                changed_cars = []
                new_car_list = []

                for car in car_list:
                    existing_car = known_cars.get(car.car_id)
                    if existing_car:
                        # машины, собранные до появления колонки brand, получают
                        # марку при первом же обновлении, без отдельной миграции данных
                        if car.brand and existing_car.brand != car.brand:
                            existing_car.brand = car.brand

                        new_price = car.price
                        old_price = existing_car.price

                        if old_price != new_price:
                            print(f'{old_price} {new_price}')

                            existing_car.price = new_price
                            existing_car.monthly_payment = car.monthly_payment
                            existing_car.city = car.city
                            existing_car.mileage = car.mileage
                            existing_car.year = car.year
                            changed_cars.append((existing_car, old_price))

                    else:
                        car.source = source
                        known_cars[car.car_id] = car
                        new_car_list.append(car)
                        session.add(car)
                        session.add(_starting_price_entry(car))

                price_drops = self._record_price_changes(session, changed_cars)
                session.commit()

                # Машины, появившиеся на сайте за время обхода, поиск новых уже
                # не увидит: они в базе. Если их не объявить здесь, в канал
                # они не попадут никогда.
                if new_car_list and source_was_filled:
                    logger.info(f"{self.source.name}: обновление цен нашло новых машин: {len(new_car_list)}")
                    await self._announce_new_cars(session, new_car_list)
                elif new_car_list:
                    logger.info(f"{self.source.name}: первое заполнение, добавлено молча: {len(new_car_list)}")

                if price_drops:
                    await self.notify_changes(price_drops)

            except Exception as e:
                session.rollback()
                logger.error(f"❌ Ошибка: {e}")
                problem = problem or f"ошибка сохранения: {_short_error(e)}"
            finally:
                session.close()

            await self._report(self.updated_cars_health, problem)

    async def _announce_new_cars(self, session, cars: List[Car]):
        """Отправляет новые машины и запоминает id постов для ссылок из снижений."""
        posted = await self.notify_new(cars)
        for car in cars:
            if car.car_id in posted:
                car.post_message_id = posted[car.car_id]
        session.commit()

    def _record_price_changes(self, session, changed_cars) -> List[PriceDrop]:
        """Пишет смены цен в историю и отбирает снижения для уведомления."""
        if not changed_cars:
            return []

        histories = _load_price_histories(session, {car.car_id for car, _ in changed_cars})
        price_drops = []
        below_threshold = 0

        for car, old_price in changed_cars:
            history = histories.setdefault(car.car_id, [])
            if not history:
                # машина собрана до того, как начали вести историю:
                # её прежняя цена и есть отправная точка
                baseline = PriceHistory(car_id=car.car_id, price=old_price, is_reference=True,
                                        created_at=car.created_at)
                session.add(baseline)
                history.append(baseline)

            entry = PriceHistory(car_id=car.car_id, price=car.price, monthly_payment=car.monthly_payment)
            session.add(entry)
            history.append(entry)

            # Отправной точкой может быть только цена с суммой: иначе машина,
            # у которой сначала стоял "Аукцион", не дала бы ни одного уведомления.
            priced_history = [row for row in history[:-1] if _has_price(row.price)]
            if not priced_history or not _has_price(car.price):
                continue
            # цена выросла — только запись в историю
            if _has_price(old_price) and not _is_price_drop(old_price, car.price):
                continue

            # Сравниваем не с предыдущей ценой, а с той, что видели читатели:
            # иначе снижения на 3% и ещё на 3% оба остались бы под порогом в 5%.
            reference = next((row for row in reversed(priced_history) if row.is_reference), priced_history[0])
            if not _is_price_drop(reference.price, car.price):
                continue

            price_drop = PriceDrop(car, reference.price, first_price=priced_history[0].price,
                                   drop_count=_count_drops(priced_history + [entry]))
            if get_drop_percent(price_drop) < Config.NOTIFY_PRICE_DROP_PERCENT:
                below_threshold += 1
                continue

            entry.is_reference = True
            price_drops.append(price_drop)

        if below_threshold:
            logger.info(f"Снижений меньше {Config.NOTIFY_PRICE_DROP_PERCENT}%: {below_threshold} — без уведомления")
        return price_drops

    def _check_scraped(self, car_list, errors_before: int, previous_count: Optional[int] = None) -> Optional[str]:
        """Причина считать запуск неудачным или None, если всё в порядке."""
        # Сначала неудачные запросы: пустой сбор обычно их следствие,
        # и в алерте полезнее текст ошибки, чем просто "0 машин".
        failed_requests = self.source_processor.error_count - errors_before
        if failed_requests:
            return (f"запросов не прошло даже после повторов: {failed_requests}, "
                    f"последняя ошибка: {self.source_processor.last_error}")

        if not car_list:
            return "не собрано ни одной машины"

        if previous_count and len(car_list) < previous_count * UPDATED_CARS_MIN_SHARE:
            return f"собрано {len(car_list)} машин, в прошлый раз было {previous_count}"
        return None

    async def _report(self, health: SourceHealth, problem: Optional[str]):
        alert = health.record(problem)
        if problem:
            logger.warning(f"{self.source.name}, {health.mode}: {problem}")
        if alert:
            await self.notification_manager.notify_admin(alert)

    async def notify_changes(self, price_drops: List[PriceDrop]):
        """Типы из SILENT_CAR_TYPES уходят отдельной пачкой без звука: пост
        в теме есть, но телефон он не будит."""
        for silent in (False, True):
            drops = [drop for drop in price_drops
                     if Config.is_silent_type(drop.car.type) == silent]
            if not drops:
                continue
            if silent:
                logger.info(f"{self.source.name}: снижений без звука: {len(drops)}")
            await self.notification_manager.notify_price_drop(
                drops, self.price_drop_thread_id, silent=silent)

    async def notify_new(self, cars: List[Car]) -> Dict[str, int]:
        return await self.notification_manager.notify_new_car(cars, self.new_thread_id)
