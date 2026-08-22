FROM python:3.11-slim

WORKDIR /app

# Install system deps for PyMuPDF, psycopg, python-magic
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The Space sets HOME=/home/user, which this image's non-root user cannot write.
# sentence-transformers then resolves its cache under that path, the download
# raises PermissionError, and calculate_ats_score quietly drops to keyword-only
# scoring. Pin the cache somewhere we own, and fetch the weights at build time so
# a cold request never waits on a download either.
ENV HF_HOME=/app/.cache/huggingface
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY . .

# Run as non-root for security hardening
RUN useradd -m -r appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

# Alembic migrations run as a non-blocking asyncio background task in main.py
# (see _run_migrations_when_db_ready). This lets uvicorn start immediately
# without waiting for RDS — critical for the Wake-on-Visit <90s boot target.
#
# --proxy-headers: the app only ever runs behind a proxy (nginx on EC2, the
# HF router on Spaces), so trust X-Forwarded-For — otherwise every client
# shares the proxy's IP and per-IP rate limits collapse into one bucket.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]

