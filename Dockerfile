# Официальный образ Playwright: Python 3.11 + Chromium + все зависимости
FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

WORKDIR /app

# Устанавливаем Python-зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY . .

ENV PORT=5000
EXPOSE 5000

# 1 воркер — Playwright sync API не потокобезопасен.
# timeout 120 — первый запрос /api/matches может занять 20–40 секунд.
CMD gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 2 --timeout 180 app:app