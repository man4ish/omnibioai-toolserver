# omnibioai-toolserver/Dockerfile.new
FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.source=https://github.com/man4ish/omnibioai

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY toolserver/ ./toolserver/
COPY toolserver_app.py .
COPY scripts/ ./scripts/

EXPOSE 9090
CMD ["uvicorn", "toolserver_app:create_app", "--factory", "--host", "0.0.0.0", "--port", "9090"]