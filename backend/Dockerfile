FROM python:3.11-slim AS common

WORKDIR /app

# Install system deps for PyMuPDF, psycopg, python-magic
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.qdrant.txt .
RUN pip install --no-cache-dir --upgrade pip==26.3 \
    && pip install --no-cache-dir -r requirements.qdrant.txt && pip check

# Export a standalone model rather than relying on the hosting user's Hub cache.
# Runtime inference uses only this directory, including when HOME is overridden.
ENV ATS_MODEL_PATH=/app/models/all-MiniLM-L6-v2
RUN --mount=type=cache,target=/root/.cache/huggingface \
    python -c "import os; from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2', revision='1110a243fdf4706b3f48f1d95db1a4f5529b4d41').save(os.environ['ATS_MODEL_PATH'])"

COPY . .

# Run as non-root for security hardening
RUN useradd -m -r appuser && chown -R appuser /app
USER appuser

# Fail the build if the serving user cannot run inference without Hub access.
RUN HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HOME=/tmp/runtime-home \
    python -c "from app.services.ats_scorer import semantic_healthcheck; result = semantic_healthcheck(); assert result['status'] == 'ok', result"

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


# The standby AWS deployment explicitly builds this target.
FROM common AS legacy
USER root
RUN pip install --no-cache-dir -r requirements.txt && pip check
USER appuser
ENV VECTOR_BACKEND=chroma

# Hugging Face Spaces builds the final stage.
FROM common AS hosted
ENV VECTOR_BACKEND=qdrant
