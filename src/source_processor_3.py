import logging
from decimal import Decimal, InvalidOperation
from typing import List, Optional, Tuple

from base_source_processor import BaseSourceProcessor
from models import Car, Source, CarType
from parsing_utils import format_number, format_price, format_year

logger = logging.getLogger(__name__)

# Типы техники в каталоге -> наши типы. Спецтехнику, мототранспорт и
# оборудование не собираем: в CarType им нет места.
CATEGORIES = {
    CarType.PASSENGER: ['legkovoy-transport'],
    CarType.CARGO: ['gruzovoy-transport', 'avtobusy'],
    # отдельного раздела нет — прицепы лежат среди грузовых, см. _car_type
    CarType.TRAILER: [],
}

# API отдаёт не больше 100 машин за запрос
PAGE_SIZE = 100
# первая страница для поиска новых — как у остальных источников
NEW_CARS_PAGE_SIZE = 20
SORT_PARAMS = {'sort_by': 'created_at', 'sort_order': 'desc', 'include_filters': 'false'}

# id карточек этого сайта и других источников живут в одном столбце car_id,
# уникальном на всю таблицу — префикс исключает случайное совпадение
CAR_ID_PREFIX = 's3:'

# cover_image_url в ответе — путь внутри хранилища, адрес собирает фронтенд сайта
MEDIA_BASE_URL = 'https://s3.twcstorage.ru/9d522da0-public'


def _to_int(value) -> Optional[int]:
    """Цены приходят строкой с копейками: "1523000.00"."""
    try:
        return int(Decimal(str(value)))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _car_type(item: dict, category_type: CarType) -> CarType:
    subtype = (item.get('vehicle_subtype') or {}).get('name') or ''
    # полуприцепы и прицепы в каталоге — подтипы грузового транспорта
    if category_type == CarType.CARGO and 'прицеп' in subtype.lower():
        return CarType.TRAILER
    return category_type


def _parse_item(item: dict) -> Optional[dict]:
    try:
        if not item.get('id') or not item.get('title'):
            return None

        brand = (item.get('brand') or {}).get('name')
        # сайт иногда оставляет в конце названия ";" или ","
        title = item['title'].strip().rstrip(' ;,')
        # в названии обычно только модель: "Соболь" — марку добавляем сами
        if brand and not title.upper().startswith(brand.upper()):
            title = f'{brand} {title}'

        mileage = _to_int(item.get('mileage'))
        year = item.get('year')
        cover = item.get('cover_image_url')

        flags = [label for flag, label in (
            ('has_restrictions', 'Есть ограничения'),
            ('registration_terminated', 'Регистрация прекращена'),
        ) if item.get(flag)]

        return {
            'id': CAR_ID_PREFIX + str(item['id']),
            'title': title,
            'brand': brand,
            'price': format_price(_to_int(item.get('current_price')), ' ₽'),
            'city': (item.get('city') or {}).get('name'),
            'mileage': f'{format_number(mileage)} км.' if mileage else None,
            'year': format_year(year),
            'detail_url': f'/sale/view-{item["id"]}',
            'image_url': f'{MEDIA_BASE_URL}/{cover.lstrip("/")}' if cover else '',
            'flags': flags,
        }

    except Exception as e:
        logger.error(f'Не удалось разобрать карточку: {e}')
        return None


class SourceProcessor3(BaseSourceProcessor):

    def __init__(self, car_types: List[CarType], source: Source):
        super().__init__()
        self.car_types = car_types
        self.source = source

    def map_car_types(self, car_type: CarType) -> List[str]:
        return CATEGORIES.get(car_type, [])

    def scrape_updated_cars(self, max_count=100) -> List[Car]:
        cars = []
        for car_type in self.car_types:
            for category in self.map_car_types(car_type):
                seen_ids = set()
                for page_index in range(max_count):
                    page = self._fetch_page(category, page_index, PAGE_SIZE)
                    if page is None:
                        break

                    page_items, pages_total = page
                    # пока идёт обход, выдача может сдвинуться — отсекаем повторы
                    fresh_items = [item for item in page_items if item['id'] not in seen_ids]
                    seen_ids.update(item['id'] for item in fresh_items)
                    page_cars = self._to_cars(fresh_items, car_type)
                    cars += page_cars
                    logger.info(
                        f'Обновление: {len(page_cars)} собрано с категории {category}, со страницы {page_index + 1}')

                    # за последней страницей сайт отдаёт пустой список
                    if not page_items or page_index + 1 >= pages_total:
                        break
        return cars

    def scrape_new_cars(self) -> List[Car]:
        cars = []
        for car_type in self.car_types:
            for category in self.map_car_types(car_type):
                page = self._fetch_page(category, 0, NEW_CARS_PAGE_SIZE)
                new_cars = self._to_cars(page[0], car_type) if page else []
                cars += new_cars
                logger.info(f'{len(new_cars)} собрано с категории {category}')
        return cars

    def _to_cars(self, items: List[dict], category_type: CarType) -> List[Car]:
        cars = []
        for item in items:
            car_data = _parse_item(item)
            if car_data:
                car = Car.from_dict(car_data)
                car.type = _car_type(item, category_type)
                cars.append(car)
        return cars

    def _fetch_page(self, category: str, page_index: int, size: int) -> Optional[Tuple[List[dict], int]]:
        params = {'vehicle_type': category, 'page': page_index, 'size': size, **SORT_PARAMS}
        response = self._get(self.source.template_url, params=params)
        if response is None:
            return None

        try:
            data = response.json()
        except ValueError as e:
            data = {'error': f'ответ не JSON: {e}'}

        # при сбое своего бэкенда сайт отвечает 200, а ошибку кладёт в поле error
        if data.get('error'):
            self.error_count += 1
            self.last_error = f'{response.url}: {data["error"]}'
            logger.error(self.last_error)
            return None

        items = data.get('items') or []
        pages_total = (data.get('pagination') or {}).get('pages') or 0
        logger.info(
            f'GET {response.url} -> status={response.status_code}, '
            f'bytes={len(response.content)}, items={len(items)}, страниц={pages_total}')
        return items, pages_total
