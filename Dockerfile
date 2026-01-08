# Poller service Dockerfile

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# System dependencies (required for psycopg / crypto libs)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency definition first (for Docker layer caching)
COPY pyproject.toml requirements.txt /app/

# Upgrade pip and install Python dependencies
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . /app/

# Run the poller
CMD ["python", "-m", "poller"]
