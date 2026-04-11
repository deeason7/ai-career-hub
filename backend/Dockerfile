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

# exec replaces sh with uvicorn as PID 1 so Docker SIGTERM is forwarded
# and in-flight requests complete before the container stops.
# Retry alembic until DB is ready (RDS takes time to start after EC2).
# Without this, the container crashes → Docker exponential backoff (up to 30s between retries).
# With this, the container stays alive and polls every 5s until RDS accepts connections.
CMD ["sh", "-c", "until alembic upgrade head; do echo '[startup] DB not ready yet, retrying in 5s...'; sleep 5; done && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
