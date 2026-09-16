import logging
import time
from abc import ABC, abstractmethod
from typing import List, Optional

import requests

from config import Config
from models import Car, CarType

logger = logging.getLogger(__name__)


class BaseSourceProcessor(ABC):
    # Страницы источников приходят медленно, а на частые запросы подряд
    # сайты отвечают обрывом соединения — отсюда таймаут, пауза и ретраи.
    REQUEST_TIMEOUT_SECONDS = 60
    REQUEST_DELAY_SECONDS = 2
    REQUEST_RETRIES = 3
    REQUEST_RETRY_DELAY_SECONDS = 5

    def __init__(self):
        self.error_count = 0
        self.session = requests.Session()
        self.session.headers.update(Config.HEADERS)
        self.last_request_time = 0.0

    @abstractmethod
    def scrape_new_cars(self) -> List[Car]:
        pass

    @abstractmethod
    def scrape_updated_cars(self) -> List[Car]:
        pass

    @abstractmethod
    def map_car_types(self, car_type: CarType):
        pass

    def _get(self, url: str, **kwargs) -> Optional[requests.Response]:
        """GET с паузой между запросами и повтором при сбое.

        Обрыв соединения случается уже во время чтения тела ответа, поэтому
        повторяется запрос целиком, а не только его установка.
        """
        for attempt in range(1, self.REQUEST_RETRIES + 1):
            try:
                self._wait_before_request()
                response = self.session.get(url, timeout=self.REQUEST_TIMEOUT_SECONDS, **kwargs)
                self.last_request_time = time.time()
                response.raise_for_status()
                return response

            except requests.RequestException as e:
                self.last_request_time = time.time()
                if attempt == self.REQUEST_RETRIES:
                    self.error_count += 1
                    logger.error(e)
                    return None
                logger.warning(f'Попытка {attempt} из {self.REQUEST_RETRIES} для {url} не удалась: {e}')
                time.sleep(self.REQUEST_RETRY_DELAY_SECONDS * attempt)

    def _wait_before_request(self):
        delay = self.REQUEST_DELAY_SECONDS - (time.time() - self.last_request_time)
        if delay > 0:
            time.sleep(delay)
