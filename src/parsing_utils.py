import re
from html import unescape
from typing import Optional


def to_int(value) -> Optional[int]:
    try:
        return int(str(value).replace(' ', '').replace('\xa0', ''))
    except (TypeError, ValueError):
        return None


def format_number(value) -> Optional[str]:
    """1234567 -> '1 234 567'"""
    number = to_int(value)
    return None if number is None else f'{number:,}'.replace(',', ' ')


def format_price(value, suffix: str) -> Optional[str]:
    number = to_int(value)
    if number is None or number <= 0:
        return None
    return format_number(number) + suffix


def normalize(text) -> str:
    return ' '.join(unescape(str(text or '')).split())


def format_year(value) -> Optional[str]:
    """Год выпуска в виде "2024 г.". Сайты иногда пишут диапазон или
    приписку ("2024-2025", "2023, рестайлинг") — берём первый год."""
    # не выдираем год из длинного числа: '19999' — не год
    match = re.search(r'(?<!\d)(19|20)\d{2}(?!\d)', str(value or ''))
    return f'{match.group(0)} г.' if match else None
