FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

# Use Python built-in urllib for health check (no curl needed in slim image)
HEALTHCHECK CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
