FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY . .

# data/ не попадает в образ: sources.json расшифровывается при деплое
# и прокидывается в контейнер томом из docker-compose.yml
RUN mkdir -p /app/data
ENV SOURCES_PATH=/app/data/sources.json

CMD ["sh", "-c", "until pg_isready -h postgres -p 5432; do echo 'Waiting for DB...'; sleep 2; done && python scripts/init_db.py && python src/main.py"]
