# ---------- Builder stage ----------
FROM python:3.11-slim AS builder

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# System deps required for building wheels
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first (for layer caching)
COPY requirements.txt /app/

# Build wheels
RUN pip install --upgrade pip \
    && pip wheel --no-cache-dir --no-deps -r requirements.txt -w /wheels


# ---------- Runtime stage ----------
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Runtime-only system deps
RUN apt-get update && apt-get install -y \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps from wheels
COPY --from=builder /wheels /wheels
RUN pip install --upgrade pip \
    && pip install --no-cache-dir /wheels/*

# Copy application code
COPY . /app/

# Run FastAPI
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
