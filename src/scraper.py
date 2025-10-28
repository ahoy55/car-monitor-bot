import random

import requests
from bs4 import BeautifulSoup
from config import Config
import logging
import time

logger = logging.getLogger(__name__)


class Scraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(Config.HEADERS)

    def scrape_new(self, car_type):
        if Config.IS_DEBUG:
            path = f"{Config.DEBUG_DIR}/page-new.html"
            html = open(path, 'r', encoding='utf-8')
            soup = BeautifulSoup(html.read(), 'html.parser')
            return self.parse_cars(soup)
        else:
            if car_type == 2:
                url = f"{Config.TYPE_2_URL}1"
            elif car_type == 4:
                url = f"{Config.TYPE_4_URL}1"
            else:
                url = ""

            try:
                form_data = {
                    'ajax': 'y',
                    'sort': 'dateDesc',
                    'count': '16',
                }

                headers = {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-Requested-With': 'XMLHttpRequest'  # если AJAX
                }

                response = self.session.get(url, data=form_data, headers=headers)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, 'html.parser')
                return self.parse_cars(soup)

            except requests.RequestException as e:
                logger.error(f"Ошибка запроса страницы новых авто: {e}")
                return []

    def scrape_page(self, page=1, car_type=4):
        """Парсинг одной страницы с пагинацией"""

        if Config.IS_DEBUG:
            try:
                path = f"{Config.DEBUG_DIR}/page-{page}.html"
                html = open(path, 'r', encoding='utf-8')
                soup = BeautifulSoup(html.read(), 'html.parser')
                return self.parse_cars(soup)

            except OSError:
                return []
        else:
            if car_type == 2:
                url = f"{Config.TYPE_2_URL}{page}"
            elif car_type == 4:
                url = f"{Config.TYPE_4_URL}{page}"
            else:
                url = ""
            try:
                response = self.session.get(url)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, 'html.parser')
                return self.parse_cars(soup)

            except requests.RequestException as e:
                logger.error(f"Ошибка запроса страницы {page}: {e}")
                return []

    def parse_cars(self, soup):
        """Парсинг автомобилей со страницы"""
        cars_with_data_item = soup.find_all(attrs={"data-item": True})

        car_elements = []
        for element in cars_with_data_item:
            text = element.get_text()
            if any(keyword in text for keyword in ['₽', 'км', 'г.', 'Покупка', 'Лизинг']):
                car_elements.append(element)

        cars_list = []

        for car in car_elements:
            car_data = self.parse_car_element(car)
            if car_data:
                cars_list.append(car_data)

        return cars_list

    def parse_car_element(self, car_element):
        """Парсинг одного элемента автомобиля"""
        try:
            car_data = {'id': car_element.get('data-item', '')}

            # Флаги
            flags = []
            flag_elements = car_element.find_all('div', class_='t-market-item-flags-item')
            for flag in flag_elements:
                flags.append(flag.get_text(strip=True))
            car_data['flags'] = flags

            # Ссылка
            link_element = car_element.find('a', class_='t-market-item-slider-item')
            if link_element:
                car_data['detail_url'] = link_element.get('href', '')

            # Изображение
            img_element = car_element.find('div', class_='t-market-item-slider-item')
            if img_element and 'style' in img_element.attrs:
                style = img_element['style']
                if 'background-image: url("' in style:
                    car_data['image_url'] = style.split('background-image: url("')[1].split('")')[0]

            # Цены
            price_element = car_element.find('div', class_='t-market-auto-month-price')
            if price_element:
                car_data['price'] = price_element.get_text(strip=True)

            monthly_price_element = car_element.find('div', class_='t-market-auto-full-price')
            if monthly_price_element:
                car_data['monthly_payment'] = monthly_price_element.get_text(strip=True)

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

        except Exception as e:
            logger.error(f"Ошибка парсинга элемента: {e}")
            return None

    def scrape_all_pages(self, max_pages=10, car_type=4):
        """Парсинг всех страниц с пагинацией"""
        all_cars = []
        scraped_page_count = 0

        for page in range(1, max_pages):
            logger.info(f"Парсинг страницы {page}...")
            cars = self.scrape_page(page, car_type)
            logger.info(f"Собрано {len(cars)} автомобилей")
            if not cars:
                break

            all_cars.extend(cars)
            time.sleep(1)  # Задержка между запросами
            scraped_page_count += 1

        logger.info(f"Всего собрано {len(all_cars)} автомобилей с {scraped_page_count} страниц")
        return all_cars

    def scrape_page_new(self, car_type=2):
        """Парсинг всех первой страницы"""
        logger.info(f"Парсинг новых автомобилей...")
        cars = self.scrape_new(car_type)

        logger.info(f"Всего собрано {len(cars)} автомобилей с страницы новых")
        return cars
