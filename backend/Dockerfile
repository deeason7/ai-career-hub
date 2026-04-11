FROM python:3.11-slim

WORKDIR /app

# Install system deps for PyMuPDF, psycopg, python-magic
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as non-root for security hardening
RUN useradd -m -r appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

# Alembic migrations run as a non-blocking asyncio background task in main.py
# (see _run_migrations_when_db_ready). This lets uvicorn start immediately
# without waiting for RDS — critical for the Wake-on-Visit <90s boot target.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

