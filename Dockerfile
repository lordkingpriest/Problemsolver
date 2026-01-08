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
COPY requirements.txt .

# Build wheels
RUN pip install --upgrade pip \
&& pip wheel --no-cache-dir -r requirements.txt -w /wheels

# ---------- Runtime stage ----------
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Runtime-only system deps
RUN apt-get update && apt-get install -y \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps from wheels
COPY --from=builder /wheels /wheels
COPY requirements.txt /app/requirements.txt

RUN pip install --upgrade pip \
    && pip install --no-cache-dir \
       --no-index \
       --find-links=/wheels \
       -r /app/requirements.txt
# Copy application code (excluding files like requirements.txt)
COPY --chown=appuser:appuser \
    app/ \
    static/ \
    templates/ \
    alembic.ini \
    ./
# Copy application code
COPY . .

# Create non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Run FastAPI
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
