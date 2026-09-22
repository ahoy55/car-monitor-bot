import logging
from typing import List, Optional, Tuple

from bs4 import BeautifulSoup

from base_source_processor import BaseSourceProcessor
from models import Car, Source, CarType
from parsing_utils import format_number, format_price, format_year, normalize

logger = logging.getLogger(__name__)

# Разделы каталога по типам. Сельхозтехнику и оборудование не собираем:
# в CarType им нет места, а расширение enum требует миграции базы.
CATEGORIES = {
    CarType.PASSENGER: ['legkovoy-avtotransport'],
    CarType.CARGO: [
        'legkiy-kommercheskiy-transport',
        'gruzovoy-avtotransport-i-avtobusy',
        'samosvaly',
        'tyagachi',
    ],
    CarType.TRAILER: [],
}

# Первая страница раздела отдаётся без параметров, следующие догружаются
# AJAX-ом: тот же список карточек без обвязки страницы, ~65 КБ.
PAGE_PARAM = 'PAGEN_2'
AJAX_PARAMS = {'ajaxload': 'y'}

# id карточек этого сайта и первого источника живут в одном столбце car_id,
# уникальном на всю таблицу — префикс исключает случайное совпадение.
CAR_ID_PREFIX = 's2:'

# Названия характеристик в карточке -> поля модели Car
PROP_TITLES = {
    'Пробег, км': 'mileage',
    'Год выпуска': 'year',
    'Марка': 'brand',
}

AUCTION_PRICE = 'Аукцион'


def _price_number(text: str) -> Optional[int]:
    digits = ''.join(c for c in text if c.isdigit())
    return int(digits) if digits else None


def _parse_prices(card) -> dict:
    """Цена и платёж различаются только подписью, порядок и набор блоков
    у карточек разный: обычная продажа, торги с текущей ценой, продажа
    без платежа и внешний аукцион вовсе без суммы."""
    parsed = {}
    for price_block in card.select('.realization__item-price'):
        value_element = price_block.find(class_='realization__item-price-val', recursive=False)
        desc_element = price_block.find(class_='realization__item-price-desc', recursive=False)
        if not value_element:
            continue

        value = normalize(value_element.get_text(' '))
        desc = normalize(desc_element.get_text(' ')).lower() if desc_element else ''
        number = _price_number(value)

        if 'в месяц' in desc:
            parsed.setdefault('monthly_payment', format_price(number, ' ₽/мес'))
        elif number is not None:
            parsed.setdefault('price', format_price(number, ' ₽'))
        else:
            parsed.setdefault('price', AUCTION_PRICE)

    parsed['price'] = parsed.get('price') or parsed.get('monthly_payment')
    return parsed


def _parse_props(card) -> dict:
    parsed = {}
    for prop in card.select('.realization__item-prop'):
        name_element = prop.select_one('.realization__item-prop-name')
        value_element = prop.select_one('.realization__item-prop-val')
        if not name_element or not value_element:
            continue

        field = PROP_TITLES.get(normalize(name_element.get_text(' ')))
        value = normalize(value_element.get_text(' '))
        if not field or not value:
            continue

        if field == 'mileage':
            value = f'{format_number(value) or value} км.'
        elif field == 'year':
            value = format_year(value)
        if value:
            parsed[field] = value
    return parsed


def _parse_card(card) -> Optional[dict]:
    try:
        id_element = card.select_one('.add-favourite[data-offer-id]')
        title_element = card.select_one('.realization__item-name')
        if not id_element or not title_element:
            return None

        link_element = card.select_one('.realization__item-buttons a[href]')
        image_element = card.select_one('.realization__slider-container img[src]')
        location_element = card.select_one('.realization__item-body > .realization__item-location')

        city = normalize(location_element.get_text(' ')) if location_element else None
        if city and city.startswith('г. '):
            city = city[3:]

        car_data = {
            'id': CAR_ID_PREFIX + id_element['data-offer-id'],
            'title': normalize(title_element.get_text(' ')),
            # у лотов внешних торгов ссылка абсолютная, у остальных — относительная
            'detail_url': link_element['href'] if link_element else '',
            'image_url': image_element['src'] if image_element else '',
            'city': city or None,
            'flags': [
                label for label in (
                    normalize(action.get_text(' '))
                    for action in card.select('.realization__item-price-action')
                ) if label
            ],
        }
        car_data.update(_parse_prices(card))
        car_data.update(_parse_props(card))
        return car_data

    except Exception as e:
        logger.error(f'Не удалось разобрать карточку: {e}')
        return None


def _parse_page(soup) -> Tuple[List[Car], bool]:
    cars_list = []
    for card in soup.select('.realization__item'):
        car_data = _parse_card(card)
        if car_data:
            cars_list.append(car_data)

    # на последней странице кнопки "показать ещё" нет
    has_next = soup.select_one('.add-new-page[url]') is not None
    return list(map(Car.from_dict, cars_list)), has_next


class SourceProcessor2(BaseSourceProcessor):

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
                for page_index in range(1, max_count + 1):
                    page = self._fetch_page(category, page_index)
                    if page is None:
                        break

                    page_cars, has_next = page
                    # За последней страницей сайт молча отдаёт первую, а пока
                    # идёт обход, выдача может сдвинуться — отсекаем повторы.
                    fresh_cars = [car for car in page_cars if car.car_id not in seen_ids]
                    if not fresh_cars:
                        logger.info(
                            f'Категория {category}: страница {page_index} повторяет уже собранные '
                            f'— переходим к следующей категории')
                        break

                    for car in fresh_cars:
                        car.type = car_type
                        seen_ids.add(car.car_id)
                    cars += fresh_cars
                    logger.info(
                        f'Обновление: {len(fresh_cars)} собрано с категории {category}, со страницы {page_index}')

                    if not has_next:
                        break
        return cars

    def scrape_new_cars(self) -> List[Car]:
        cars = []
        for car_type in self.car_types:
            for category in self.map_car_types(car_type):
                page = self._fetch_page(category, 1)
                new_cars = page[0] if page else []
                for new_car in new_cars:
                    new_car.type = car_type
                cars += new_cars
                logger.info(f'{len(new_cars)} собрано с категории {category}')
        return cars

    def _fetch_page(self, category: str, page_index: int) -> Optional[Tuple[List[Car], bool]]:
        url = self.source.template_url % category
        params = None if page_index == 1 else {PAGE_PARAM: page_index, **AJAX_PARAMS}

        response = self._get(url, params=params)
        if response is None:
            return None

        page_cars, has_next = _parse_page(BeautifulSoup(response.text, 'html.parser'))
        logger.info(
            f'GET {response.url} -> status={response.status_code}, '
            f'bytes={len(response.text)}, items={len(page_cars)}, '
            f'следующая={"есть" if has_next else "нет"}')
        return page_cars, has_next
