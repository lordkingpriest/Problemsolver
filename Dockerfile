# Poller service Dockerfile
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
 && rm -rf /var/lib/apt/lists/*

# Copy dependency definition
COPY pyproject.toml /app/

# Install dependencies
RUN pip install --upgrade pip \
 && pip install --no-cache-dir .

# Copy application code
COPY . /app

# Run poller
CMD ["python", "-m", "app.poller.main"]
