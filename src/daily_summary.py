from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from html import escape
from typing import Dict, List, Tuple

import pytz

from bot.templates import _calculate_drop_percent, _format_percent, absolute_url
from models import Car, CarType, PriceHistory, Source

MOSCOW = pytz.timezone('Europe/Moscow')
TOP_DROPS = 5

TYPE_LABELS = [
    (CarType.CARGO, '🚛 грузовые'),
    (CarType.TRAILER, '🚜 прицепы'),
    (CarType.PASSENGER, '🚗 легковые'),
]

MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля',
          'августа', 'сентября', 'октября', 'ноября', 'декабря']


def _moscow_day_bounds(day: date) -> Tuple[datetime, datetime]:
    """Границы московских суток в часах процесса.

    created_at пишется через datetime.now() — это часы контейнера, на сервере
    UTC. Смещение считаем, а не зашиваем +3: так итоги не съедут, если у
    контейнера поменяют часовой пояс.
    """
    offset = datetime.now() - datetime.now(MOSCOW).replace(tzinfo=None)
    # убираем разницу в микросекундах между двумя вызовами now()
    offset = timedelta(minutes=round(offset.total_seconds() / 60))
    start = datetime.combine(day, time.min) + offset
    return start, start + timedelta(days=1)


def _new_cars(session, start: datetime, end: datetime) -> Dict[int, Counter]:
    counts = defaultdict(Counter)
    rows = (session.query(Car.source_id, Car.type)
            .filter(Car.created_at >= start, Car.created_at < end))
    for source_id, car_type in rows:
        counts[source_id][car_type] += 1
    return counts


def _price_drops(session, start: datetime, end: datetime) -> List[Tuple[Car, str, float]]:
    """Снижения, о которых за сутки ушло уведомление: (машина, цена до, %).

    Уведомлённое снижение — отправная точка в истории, которая не первая
    запись машины (первая — это стартовая цена при появлении).
    """
    todays = (session.query(PriceHistory)
              .filter(PriceHistory.is_reference.is_(True),
                      PriceHistory.created_at >= start, PriceHistory.created_at < end)
              .all())
    if not todays:
        return []

    car_ids = {row.car_id for row in todays}
    history = defaultdict(list)
    for row in (session.query(PriceHistory)
                .filter(PriceHistory.car_id.in_(car_ids), PriceHistory.is_reference.is_(True))
                .order_by(PriceHistory.created_at, PriceHistory.id)):
        history[row.car_id].append(row)
    cars = {car.car_id: car for car in session.query(Car).filter(Car.car_id.in_(car_ids))}

    drops = []
    for row in todays:
        rows = history[row.car_id]
        index = rows.index(row)
        car = cars.get(row.car_id)
        if index == 0 or car is None:
            continue
        previous = rows[index - 1].price
        percent = _calculate_drop_percent(previous, row.price)
        if percent > 0:
            drops.append((car, previous, percent))
    return drops


def _day_title(day: date) -> str:
    return f"{day.day} {MONTHS[day.month - 1]}"


def build_daily_summary(session, day: date) -> str:
    start, end = _moscow_day_bounds(day)
    new_cars = _new_cars(session, start, end)
    drops = _price_drops(session, start, end)

    drops_by_source = Counter(car.source_id for car, _, _ in drops)
    lines = [f"📊 <b>Итоги дня · {_day_title(day)}</b>", ""]

    for source in session.query(Source).order_by(Source.id):
        new_by_type = new_cars.get(source.id, Counter())
        new_total = sum(new_by_type.values())
        lines.append(f"<b>{escape(source.name)}</b>: 🆕 {new_total} · 📉 {drops_by_source[source.id]}")
        by_type = " · ".join(f"{label} {new_by_type[car_type]}"
                             for car_type, label in TYPE_LABELS if new_by_type[car_type])
        if by_type:
            lines.append(f"    {by_type}")

    if drops:
        lines += ["", "🔥 <b>Лучшие снижения</b>"]
        top = sorted(drops, key=lambda drop: drop[2], reverse=True)[:TOP_DROPS]
        for number, (car, previous, percent) in enumerate(top, start=1):
            link = escape(absolute_url(car, car.detail_url))
            lines.append(
                f"{number}. <a href='{link}'>{escape(car.title or '')}</a> · −{_format_percent(percent)}% · "
                f"{escape(car.price or '')} · {escape(car.source.name)}")
    elif not new_cars:
        lines.append("Новых машин и снижений цен не было.")

    return "\n".join(lines)
