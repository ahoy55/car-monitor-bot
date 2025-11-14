from dataclasses import dataclass
from typing import List

from models import Car
from models import CarType


@dataclass
class PriceDrop:
    car: Car
    old_price: str


def _calculate_drop_percent(old_price: str, new_price: str):
    try:
        # Убираем всё кроме цифр
        old_clean = ''.join(c for c in old_price if c.isdigit())
        new_clean = ''.join(c for c in new_price if c.isdigit())

        int_old_price = int(old_clean)
        int_new_price = int(new_clean)

        if int_old_price > 0:
            return (int_old_price - int_new_price) / int_old_price * 100

    except (ValueError, ZeroDivisionError):
        pass

    return 0


def _get_vehicle_type(car):
    if car.type == CarType.PASSENGER:
        return "легковые"
    elif car.type == CarType.CARGO:
        return "грузовые"
    elif car.type == CarType.TRAILER:
        return "прицеп"
    else:
        return None


def format_multiple_new_cars_messages(cars: list) -> list:
    """Форматирование сообщения о нескольких новых автомобилях"""
    messages = [format_new_cars_message(car) for car in cars]
    messages[0] = get_new_cars_title(len(cars)) + messages[0]
    return messages


def format_new_cars_message(car):
    return (f"🖥 <b>Источник:</b> {car.source.name}\n"
            f"🚛 <b>Тип:</b> {_get_vehicle_type(car)}\n"
            f"🚗 {car.title}\n"
            f"💰 {car.price}\n"
            f"🔗 <a href='{car.source.base_url}{car.detail_url}'>Посмотреть на сайте</a>")


def get_new_cars_title(count):
    if count % 10 == 1 and count % 100 != 11:
        count_text = "новый автомобиль"
    elif count % 10 in [2, 3, 4] and count % 100 not in [12, 13, 14]:
        count_text = "новых автомобиля"
    else:
        count_text = "новых автомобилей"

    return f"🆕 <b>{count} {count_text}!</b>\n\n"


def get_price_drops_title(count):
    # Склонение для снижений цен
    if count % 10 == 1 and count % 100 != 11:
        count_text = "снижение цены"
    elif count % 10 in [2, 3, 4] and count % 100 not in [12, 13, 14]:
        count_text = "снижения цен"
    else:
        count_text = "снижений цен"

    return f"📉 <b>{count} {count_text}!</b>\n\n"


def format_price_drops_message(price_drop: PriceDrop):
    car = price_drop.car
    old_price = price_drop.old_price
    drop_percent = _calculate_drop_percent(old_price, car.price)
    return (
        f"🖥 <b>Источник:</b> {car.source.name}\n"
        f"🚛 <b>Тип:</b> {_get_vehicle_type(car)}\n"
        f"🚗 {car.title}\n"
        f"💰 <s>{old_price}</s> → <b>{car.price}</b> (-{drop_percent:.01f}%)\n"
        f"🔗 <a href='{car.source.base_url}{car.detail_url}'>Посмотреть на сайте</a>"
    )


def format_multiple_price_drops_messages(price_drops: List[PriceDrop]) -> list:
    """Форматирование сообщения о нескольких снижениях цен"""
    messages = [format_price_drops_message(price_drop) for price_drop in price_drops]
    messages[0] = get_price_drops_title(len(price_drops)) + messages[0]
    return messages
