# Dockerfile
FROM python:3.14.3-slim

WORKDIR /app

COPY requirements.txt .

RUN apt-get update && apt-get install -y netcat-openbsd && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

COPY entrypoint.sh .

ENTRYPOINT ["./entrypoint.sh"]