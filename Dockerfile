FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential && \
    rm -rf /var/lib/apt/lists/*

# Python deps
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

# App code
COPY config/ config/
COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .

# Create directories
RUN mkdir -p training_outputs cache

EXPOSE 8000

# Run with uvicorn (production)
CMD ["uvicorn", "a1.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--log-level", "info"]
