import re
from dataclasses import dataclass
from html import escape
from typing import List

from models import Car
from models import CarType
from parsing_utils import format_number


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


def get_drop_percent(price_drop: PriceDrop) -> float:
    return _calculate_drop_percent(price_drop.old_price, price_drop.car.price)


def _get_drop_amount(price_drop: PriceDrop) -> int:
    old_price = ''.join(c for c in price_drop.old_price if c.isdigit())
    new_price = ''.join(c for c in price_drop.car.price if c.isdigit())
    return int(old_price or 0) - int(new_price or 0)


def absolute_url(car: Car, url: str) -> str:
    # у лотов внешних торгов ссылка абсолютная, у остальных — от корня сайта
    url = url or ""
    if url.startswith(("http://", "https://")):
        return url
    return f"{car.source.base_url}{url}"


def _get_vehicle_type(car):
    if car.type == CarType.PASSENGER:
        return "легковые"
    elif car.type == CarType.CARGO:
        return "грузовые"
    elif car.type == CarType.TRAILER:
        return "прицепы"
    else:
        return None


def format_multiple_new_cars_messages(cars: list, more=False) -> list:
    """Форматирование сообщения о нескольких новых автомобилях"""
    messages = [format_new_cars_message(car) for car in cars]
    messages[0] = get_new_cars_title(len(cars), more) + messages[0]
    return messages


def format_new_cars_message(car):
    return format_common_message(car, escape(car.price or ""))


def format_separate_new_car_message(car):
    # отдельное сообщение пересылают и находят по тегу вне темы —
    # заголовок сразу говорит, что это новое предложение
    return "🆕 <b>Новое предложение</b>\n" + format_new_cars_message(car)


def get_new_cars_title(count, more=False):
    if count % 10 == 1 and count % 100 != 11:
        count_text = "новый автомобиль"
    elif count % 10 in [2, 3, 4] and count % 100 not in [12, 13, 14]:
        count_text = "новых автомобиля"
    else:
        count_text = "новых автомобилей"

    # "ещё" — когда первые машины уже ушли отдельными сообщениями
    prefix = "Ещё " if more else ""
    return f"🆕 <b>{prefix}{count} {count_text}!</b>\n\n"


def get_price_drops_title(count, more=False):
    # Склонение для снижений цен
    if count % 10 == 1 and count % 100 != 11:
        count_text = "снижение цены"
    elif count % 10 in [2, 3, 4] and count % 100 not in [12, 13, 14]:
        count_text = "снижения цен"
    else:
        count_text = "снижений цен"

    # "ещё" — когда лучшие снижения уже ушли отдельными сообщениями
    prefix = "Ещё " if more else ""
    return f"📉 <b>{prefix}{count} {count_text}!</b>\n\n"


def format_price_drops_message(price_drop: PriceDrop):
    car = price_drop.car
    # выгода — первой строкой: по ней решают, открывать ли карточку
    drop_percent = f"{get_drop_percent(price_drop):.1f}".replace(".", ",")
    headline = f"📉 <b>−{format_number(_get_drop_amount(price_drop))} ₽ (−{drop_percent}%)</b>\n"
    price_text = f"<s>{escape(price_drop.old_price)}</s> → <b>{escape(car.price)}</b>"
    return headline + format_common_message(car, price_text)


def format_multiple_price_drops_messages(price_drops: List[PriceDrop], more=False) -> list:
    """Форматирование сообщения о нескольких снижениях цен"""
    messages = [format_price_drops_message(price_drop) for price_drop in price_drops]
    messages[0] = get_price_drops_title(len(price_drops), more) + messages[0]
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
    detail_url = absolute_url(car, car.detail_url)

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