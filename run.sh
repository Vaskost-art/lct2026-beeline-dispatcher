#!/usr/bin/env bash
# Запуск прототипа одной командой: ./run.sh [порт]
set -euo pipefail

PORT="${1:-8000}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

if [ ! -d .venv ]; then
  echo "Создаю виртуальное окружение…"
  python3 -m venv .venv
  ./.venv/bin/pip install --quiet --upgrade pip
  ./.venv/bin/pip install --quiet -r requirements.txt
fi

# Ключи Яндекса живут в .env (он в .gitignore). Сервис читает файл и сам,
# но здесь тоже подхватываем — тогда переменные видны и дочерним процессам.
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

if [ -z "${YANDEX_MAPS_API_KEY:-}" ]; then
  echo "Ключ Яндекс Карт не задан — карта будет собственной схемой."
  echo "Чтобы включить Яндекс Карты: cp .env.example .env и вписать ключ."
fi

echo "Интерфейс диспетчера: http://127.0.0.1:${PORT}"
cd backend
exec "$HERE/.venv/bin/python" -m uvicorn app:app --host 127.0.0.1 --port "$PORT"
