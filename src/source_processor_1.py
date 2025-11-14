import logging
import time
from typing import List

import requests
from bs4 import BeautifulSoup

from base_source_processor import BaseSourceProcessor
from config import Config
from models import Car, Source, CarType

logger = logging.getLogger(__name__)


def _parse_car_element(car_element):
    try:
        car_data = {'id': car_element.get('data-item', '')}

        # Флаги
        flags = []
        flag_elements = car_element.find_all('div', class_='t-market-item-flags-item')
        for flag in flag_elements:
            flags.append(flag.get_text(strip=True))
        car_data['flags'] = flags

        # Ссылка
        link_element = car_element.find('a', class_='t-loading-gray')
        if link_element:
            car_data['detail_url'] = link_element.get('href', '')

        # Изображение
        img_element = car_element.find('div', class_='t-market-item-slider-item')
        if img_element and 'style' in img_element.attrs:
            style = img_element['style']
            if 'background-image: url("' in style:
                car_data['image_url'] = style.split('background-image: url("')[1].split('")')[0]

        # Цены
        price_element = car_element.find('div', class_='t-market-auto-full-price')
        monthly_price_element = car_element.find('div', class_='t-market-auto-month-price')

        if price_element and monthly_price_element:
            price = price_element.get_text(strip=True)
            month_price = car_data['monthly_payment'] = monthly_price_element.get_text(strip=True)
            if "₽/мес" in price:
                car_data['price'] = month_price
                car_data['monthly_payment'] = price
            else:
                car_data['price'] = price
                car_data['monthly_payment'] = month_price

        # Название
        title_element = car_element.find('div', class_='t-market-auto-title')
        if title_element:
            title_link = title_element.find('a')
            if title_link:
                car_data['title'] = title_link.get_text(strip=True)

        # Свойства
        props_element = car_element.find('div', class_='t-market-auto-props')
        if props_element:
            props_text = props_element.get_text(strip=True)
            props_parts = props_text.split(' / ')
            if len(props_parts) >= 3:
                car_data['city'] = props_parts[0]
                car_data['mileage'] = props_parts[1]
                car_data['year'] = props_parts[2]

        return car_data if car_data.get('title') else None

    except Exception:
        return None


def _parse_soup_page(soup) -> List[Car]:
    cars_with_data_item = soup.find_all(attrs={"data-item": True})

    car_elements = []
    for element in cars_with_data_item:
        text = element.get_text()
        if any(keyword in text for keyword in ['₽', 'км', 'г.', 'Покупка', 'Лизинг']):
            car_elements.append(element)

    cars_list = []
    for car in car_elements:
        car_data = _parse_car_element(car)
        if car_data:
            cars_list.append(car_data)

    return list(map(Car.from_dict, cars_list))


def test():
    with open('test1.html', 'r', encoding='utf-8') as file:
        content = file.read()
        soup = BeautifulSoup(content, 'html.parser')
        new_cars = _parse_soup_page(soup)
        print("\n".join([str(car.monthly_payment) for car in new_cars]))
    print("end")

if __name__ == "__main__":
    test()

class SourceProcessor1(BaseSourceProcessor):

    def __init__(self, car_types: List[CarType], source: Source):
        super().__init__()
        self.car_types = car_types
        self.mapped_car_types = list(map(self.map_car_types, car_types))
        self.source = source
        self.session = requests.Session()
        self.session.headers.update(Config.HEADERS)

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
                print(url)
                scraped_cars = self._scrape_page(url)
                for scraped_car in scraped_cars:
                    scraped_car.type = self.car_types[i]
                cars += scraped_cars
                logger.info(
                    f'Обновление: {len(scraped_cars)} собрано с категории {str(self.car_types[i])}, со страницы {page_index}')
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

    def _scrape_page(self, url: str) -> List[Car]:
        try:
            form_data = {
                'USER_AJAX': 'Y',
                'sort': 'dateDesc',
                'count': '16',
            }

            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-Requested-With': 'XMLHttpRequest'  # если AJAX
            }

            response = self.session.post(url, data=form_data, headers=headers)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            return _parse_soup_page(soup)

        except requests.RequestException as e:
            self.error_count += 1
            logger.error(e)
            return []
