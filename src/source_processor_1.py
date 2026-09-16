import json
import logging
import re
from typing import List, Optional

from bs4 import BeautifulSoup

from base_source_processor import BaseSourceProcessor
from models import Car, Source, CarType
from parsing_utils import format_number, format_price, normalize

logger = logging.getLogger(__name__)

# С USER_AJAX=Y сайт отдаёт ту же выдачу без обвязки страницы:
# ~120 КБ вместо ~4 МБ при том же наборе машин.
AJAX_PARAMS = {'USER_AJAX': 'Y'}

# Названия характеристик в autoPropsFull -> поля модели Car
PROP_TITLES = {
    'Город': 'city',
    'Год выпуска': 'year',
    'Пробег, км': 'mileage',
}


def _parse_props(item: dict) -> dict:
    """Достаёт город, пробег и год выпуска.

    У машин с пробегом характеристики лежат в propsBU плоским списком,
    у новых — в autoPropsFull парами TITLE/VALUE, поэтому смотрим оба места.
    """
    parsed = {}

    for prop in item.get('autoPropsFull') or []:
        field = PROP_TITLES.get(normalize(prop.get('TITLE')))
        value = normalize(prop.get('VALUE'))
        if not field or not value:
            continue
        if field == 'year':
            value = f'{value} г.'
        elif field == 'mileage':
            value = f'{format_number(value) or value} км.'
        parsed[field] = value

    for prop in (item.get('propsBU') or []) + (item.get('autoProps') or []):
        text = normalize(prop)
        if 'км' in text:
            parsed.setdefault('mileage', text)
        elif re.fullmatch(r'\d{4}\s*г\.', text):
            parsed.setdefault('year', text)
        elif text and not any(c.isdigit() for c in text):
            parsed.setdefault('city', text)

    return parsed


def _parse_car_item(item: dict) -> Optional[dict]:
    try:
        if not item.get('name'):
            return None

        car_data = {
            'id': str(item.get('id', '')),
            'title': item.get('name'),
            'detail_url': item.get('detailPageUrl', ''),
            'image_url': item.get('previewPicture', ''),
            'flags': [
                shield.get('label')
                for shield in item.get('goodShields', [])
                if shield.get('condition') and shield.get('label')
            ],
        }

        # Цены: у карточек "только покупка" месячного платежа может не быть,
        # у лизинговых — полной цены; берём то, что есть.
        price = format_price(item.get('minPriceLeasing'), ' ₽')
        monthly_payment = format_price(item.get('leasingPayment'), ' ₽/мес')
        car_data['price'] = price or monthly_payment
        car_data['monthly_payment'] = monthly_payment

        car_data.update(_parse_props(item))

        return car_data if car_data.get('id') else None

    except Exception as e:
        logger.error(f'Не удалось разобрать карточку: {e}')
        return None


def _parse_catalog_data(soup) -> Optional[dict]:
    """Список машин рендерится на клиенте: в HTML он лежит JSON-ом
    в атрибуте v-bind компонента <market-catalog>."""
    catalog_element = soup.find('market-catalog')
    if not catalog_element:
        return None

    raw = catalog_element.get('v-bind')
    if not raw:
        return None

    try:
        return json.loads(raw)
    except ValueError as e:
        logger.error(f'Не удалось разобрать JSON каталога: {e}')
        return None


def _cars_from_catalog(catalog_data: dict) -> List[Car]:
    cars_list = []
    for item in catalog_data.get('initialItems', []):
        car_data = _parse_car_item(item)
        if car_data:
            cars_list.append(car_data)

    return list(map(Car.from_dict, cars_list))


def _parse_soup_page(soup) -> List[Car]:
    catalog_data = _parse_catalog_data(soup)
    if not catalog_data:
        logger.error('На странице не найден блок <market-catalog> с данными каталога')
        return []

    return _cars_from_catalog(catalog_data)


class SourceProcessor1(BaseSourceProcessor):

    def __init__(self, car_types: List[CarType], source: Source):
        super().__init__()
        self.car_types = car_types
        self.mapped_car_types = list(map(self.map_car_types, car_types))
        self.source = source

    def map_car_types(self, car_type: CarType):
        if car_type == CarType.CARGO:
            return 2
        elif car_type == CarType.PASSENGER:
            return 4
        elif car_type == CarType.TRAILER:
            return 5
        return None

    def scrape_updated_cars(self, max_count=100) -> List[Car]:
        cars = []
        for i in range(0, len(self.mapped_car_types)):
            car_type = self.mapped_car_types[i]
            for page_index in range(1, max_count + 1):
                url = self.source.template_url % (car_type, page_index)
                catalog_data = self._fetch_catalog(url)
                if not catalog_data:
                    break

                # За последней страницей сайт молча отдаёт первую —
                # без этой проверки цикл собирал бы её же до max_count.
                if catalog_data.get('pagen') != page_index:
                    logger.info(
                        f'Категория {str(self.car_types[i])}: страница {page_index} отсутствует, '
                        f'сайт вернул {catalog_data.get("pagen")} — переходим к следующей категории')
                    break

                scraped_cars = _cars_from_catalog(catalog_data)
                for scraped_car in scraped_cars:
                    scraped_car.type = self.car_types[i]
                cars += scraped_cars
                logger.info(
                    f'Обновление: {len(scraped_cars)} собрано с категории {str(self.car_types[i])}, со страницы {page_index}')

                if not scraped_cars:
                    break
        return cars

    def scrape_new_cars(self) -> List[Car]:
        cars = []
        for i in range(0, len(self.mapped_car_types)):
            car_type = self.mapped_car_types[i]
            url = self.source.template_url % (car_type, 1)
            new_cars = self._scrape_page(url)
            for new_car in new_cars:
                new_car.type = self.car_types[i]
            cars += new_cars
            logger.info(f'{len(new_cars)} собрано с категории {str(self.car_types[i])}')
        return cars

    def _fetch_catalog(self, url: str) -> Optional[dict]:
        """Скачивает страницу каталога и достаёт из неё данные списка машин."""
        response = self._get(url, params=AJAX_PARAMS)
        if response is None:
            return None

        catalog_data = _parse_catalog_data(BeautifulSoup(response.text, 'html.parser'))

        logger.info(
            f'GET {url} -> status={response.status_code}, '
            f'bytes={len(response.text)}, '
            f'market-catalog={"да" if catalog_data is not None else "нет"}, '
            f'items={len(catalog_data.get("initialItems", [])) if catalog_data else 0}')

        if catalog_data is None:
            logger.error(f'На странице {url} не найден блок <market-catalog> с данными каталога')
        return catalog_data

    def _scrape_page(self, url: str) -> List[Car]:
        catalog_data = self._fetch_catalog(url)
        if not catalog_data:
            return []
        return _cars_from_catalog(catalog_data)


def test(path='page.html'):
    with open(path, 'r', encoding='utf-8') as file:
        soup = BeautifulSoup(file.read(), 'html.parser')
        new_cars = _parse_soup_page(soup)
        for car in new_cars:
            print(f'{car.car_id} | {car.title} | {car.price} | {car.monthly_payment} | '
                  f'{car.city} | {car.mileage} | {car.year} | {car.detail_url}')
        print(f'Всего: {len(new_cars)}')


if __name__ == "__main__":
    test()
