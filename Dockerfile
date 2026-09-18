# Интерфейс собирается отдельной ступенью: в итоговый образ едет только
# готовая статика, без node_modules и инструментов сборки.
FROM node:22-alpine AS ui
WORKDIR /ui
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY --from=ui /ui/dist/ ./frontend/dist/
COPY data/ ./data/
COPY scripts/ ./scripts/

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "dispatcher.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "src"]
