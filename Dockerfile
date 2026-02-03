FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Миграции при старте, затем запуск бота. Эхо перед python — в логах видно, доходит ли выполнение до main.py.
CMD ["sh", "-c", "alembic upgrade head && echo '!!! ALEMBIC DONE, STARTING PYTHON !!!' && exec python main.py"]
