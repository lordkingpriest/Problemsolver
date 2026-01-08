# Poller service Dockerfile (multi-stage)
FROM python:3.11-slim AS base
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y build-essential libpq-dev && rm -rf /var/lib/apt/lists/*

# Copy files
COPY pyproject.toml requirements.txt /app/
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

COPY . /app

# Poller runs as: python -m app.poller.main
CMD ["python", "-m", "app.poller.main"]