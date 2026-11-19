# Single container: React dashboard + FastAPI API (demo mode when INFLUX_URL is unset)
FROM node:20-slim AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ .
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY --from=web /web/build ./static
CMD uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080}
