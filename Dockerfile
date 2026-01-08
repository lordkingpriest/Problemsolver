# Multi-stage build
FROM python:3.11-slim AS base
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y build-essential libpq-dev

COPY pyproject.toml poetry.lock* /app/
# Install dependencies (poetry or pip as per preference)
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

COPY . /app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]