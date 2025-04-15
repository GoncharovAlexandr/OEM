FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /app

RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install poetry

COPY ./backend/pyproject.toml ./backend/poetry.lock ./

RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi --no-root

COPY . .

WORKDIR /app/backend

# Убедитесь, что этот путь соответствует структуре вашего проекта
CMD ["sh", "-c", "poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]