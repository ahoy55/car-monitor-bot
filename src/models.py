from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class Car(Base):
    __tablename__ = 'cars'

    @classmethod
    def from_dict(cls, car_data: dict):
        """Создает объект Car из словаря"""
        return cls(
            car_id=car_data.get('id'),
            title=car_data.get('title'),
            price=car_data.get('price'),
            monthly_payment=' '.join(car_data.get('monthly_payment').split()),
            city=car_data.get('city'),
            mileage=car_data.get('mileage'),
            year=car_data.get('year'),
            flags=str(car_data.get('flags', [])),
            detail_url=car_data.get('detail_url'),
            image_url=car_data.get('image_url')
        )

    id = Column(Integer, primary_key=True)
    car_id = Column(String(50), unique=True, index=True)
    title = Column(String(200))
    price = Column(String(100))
    monthly_payment = Column(String(100))
    city = Column(String(100))
    mileage = Column(String(50))
    year = Column(String(10))
    flags = Column(Text)
    detail_url = Column(String(500))
    image_url = Column(String(500))
    created_at = Column(DateTime, default=datetime.now)



class PriceHistory(Base):
    __tablename__ = 'price_history'

    id = Column(Integer, primary_key=True)
    car_id = Column(String(50), index=True)
    price = Column(String(100))
    monthly_payment = Column(String(100))
    created_at = Column(DateTime, default=datetime.now)


class UserSubscription(Base):
    __tablename__ = 'user_subscriptions'

    id = Column(Integer, primary_key=True)
    chat_id = Column(String(50), unique=True, index=True)
    username = Column(String(100))
    first_name = Column(String(100))
    is_active = Column(Boolean, default=True)
    notify_price_drops = Column(Boolean, default=True)
    notify_new_cars = Column(Boolean, default=True)
    brands = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
