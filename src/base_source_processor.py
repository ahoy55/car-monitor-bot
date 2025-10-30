from abc import ABC, abstractmethod
from typing import List

from models import Car, CarType


class BaseSourceProcessor(ABC):

    def __init__(self):
        self.error_count = 0

    @abstractmethod
    def scrape_new_cars(self) -> List[Car]:
        pass

    @abstractmethod
    def scrape_updated_cars(self) -> List[Car]:
        pass

    @abstractmethod
    def map_car_types(self, car_type: CarType):
        pass
