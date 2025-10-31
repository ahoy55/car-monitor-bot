FROM python:3.11-alpine

RUN apk add --no-cache \
    gcc \
    g++ \
    musl-dev \
    postgresql-dev \
    libffi-dev \
    postgresql-client  # добавляем pg_isready

WORKDIR /app

ENV PYTHONPATH=/app/src

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data
COPY data/sources.json /app/data/sources.json

ENV SOURCES_PATH=/app/data/sources.json

CMD ["sh", "-c", "until pg_isready -h postgres -p 5432; do echo 'Waiting for DB...'; sleep 2; done && python scripts/init_db.py && python src/main.py"]
