FROM python:3.11-slim

WORKDIR /app

ENV PYTHONPATH=/app/src

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data /app/logs /app/backups

# Создаем пустой файл БД
RUN echo "" > /app/data/cars.db && chmod 666 /app/data/cars.db

# Запускаем инициализацию БД при сборке
RUN python3 scripts/init_db.py

CMD ["python", "src/main.py"]
