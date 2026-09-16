import re
from dataclasses import dataclass
from html import escape
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
        return "прицепы"
    else:
        return None


def format_multiple_new_cars_messages(cars: list) -> list:
    """Форматирование сообщения о нескольких новых автомобилях"""
    messages = [format_new_cars_message(car) for car in cars]
    messages[0] = get_new_cars_title(len(cars)) + messages[0]
    return messages


def format_new_cars_message(car):
    return format_common_message(car, escape(car.price or ""))


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
    price_text = f"<s>{escape(old_price)}</s> → <b>{escape(car.price)}</b> (-{drop_percent:.01f}%)"
    return format_common_message(car, price_text)


def format_multiple_price_drops_messages(price_drops: List[PriceDrop]) -> list:
    """Форматирование сообщения о нескольких снижениях цен"""
    messages = [format_price_drops_message(price_drop) for price_drop in price_drops]
    messages[0] = get_price_drops_title(len(price_drops)) + messages[0]
    return messages


def _hashtag(value, upper=False):
    """Хэштег Telegram: только буквы, цифры и _. Нажатие на него в канале
    показывает все сообщения с тем же тегом — фильтр без настроек."""
    tag = re.sub(r"\W+", "_", value or "").strip("_")
    if upper:
        # марки на сайтах пишут по-разному: SHACMAN и Shacman — одна марка
        tag = tag.upper()
    # тег из одних цифр Telegram ссылкой не делает
    if not tag or tag.replace("_", "").isdigit():
        return None
    return f"#{tag}"


def _monthly_payment_text(car: Car):
    # Car.from_dict пишет "0", когда платежа нет; у лотов без полной цены
    # платёж уже стоит на месте цены — второй раз его не показываем
    monthly_payment = car.monthly_payment
    if not monthly_payment or monthly_payment == "0" or monthly_payment == car.price:
        return None
    return escape(monthly_payment)


def format_common_message(car: Car, price_text):
    # лоты внешних торгов ведут сразу на площадку, ссылка у них абсолютная
    detail_url = car.detail_url or ""
    if not detail_url.startswith(("http://", "https://")):
        detail_url = f"{car.source.base_url}{detail_url}"

    tags = " ".join(tag for tag in (_hashtag(_get_vehicle_type(car)), _hashtag(car.brand, upper=True)) if tag)
    title = f"🚗 <b>{escape(car.title or '')}</b>" + (f" · {tags}" if tags else "")

    # у новых машин пробега нет, у части лотов нет года — пропускаем пустое
    city = _hashtag(car.city) or escape(car.city or "")
    year = (car.year or "").removesuffix(" г.")
    mileage = (car.mileage or "").removesuffix(".")
    details = " · ".join(part for part in (city, escape(year), escape(mileage)) if part)

    monthly_payment = _monthly_payment_text(car)
    price_line = f"💰 {price_text}" + (f" · {monthly_payment}" if monthly_payment else "")

    lines = [title]
    if details:
        lines.append(f"📍 {details}")
    lines.append(price_line)
    lines.append(f"🔗 <a href='{escape(detail_url)}'>Подробнее</a> · {escape(car.source.name)}")
    return "\n".join(lines)