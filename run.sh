#!/usr/bin/env bash
# Запуск прототипа одной командой на свежем клоне: ./run.sh [порт]
#
# Сам ставит зависимости Python и собирает интерфейс, если сборки ещё нет:
# в репозитории её нет, она собирается из frontend/. Работает в Linux, macOS
# и в Git Bash на Windows.
set -euo pipefail

PORT="${1:-8000}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

# --- Python ------------------------------------------------------------------
# Интерпретатор выбирается по тому, что он реально запускается и новее 3.11:
# в Windows `python3` часто оказывается заглушкой Магазина, которая есть в
# PATH, но ничего не исполняет.
PYTHON=""
for candidate in python3 python py; do
  if command -v "$candidate" >/dev/null 2>&1 \
     && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 11))' >/dev/null 2>&1; then
    PYTHON="$candidate"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  echo "Нужен Python 3.11 или новее. Либо запустите через Docker: docker compose up --build" >&2
  exit 1
fi

if [ ! -d .venv ]; then
  echo "Создаю виртуальное окружение…"
  "$PYTHON" -m venv .venv
fi
# В Windows окружение кладёт интерпретатор в Scripts, а не в bin.
VENV_PY=".venv/bin/python"
[ -x "$VENV_PY" ] || VENV_PY=".venv/Scripts/python.exe"

# Отметка ставится только после успешной установки: оборванная установка
# не должна выглядеть завершённой при следующем запуске.
if [ ! -f .venv/.installed ] || [ requirements.txt -nt .venv/.installed ]; then
  echo "Ставлю зависимости Python…"
  "$VENV_PY" -m pip install --quiet --upgrade pip
  "$VENV_PY" -m pip install --quiet -r requirements.txt
  touch .venv/.installed
fi

# --- Интерфейс ---------------------------------------------------------------
if [ ! -f frontend/dist/index.html ]; then
  if ! command -v npx >/dev/null 2>&1; then
    echo "Интерфейс не собран, а для сборки нужен Node.js 20 или новее." >&2
    echo "Поставьте Node.js или запустите через Docker: docker compose up --build" >&2
    exit 1
  fi
  echo "Собираю интерфейс (один раз, около минуты)…"
  # pnpm берётся той версии, что записана в package.json, без глобальной
  # установки: corepack требует прав, которых у проверяющего может не быть.
  (cd frontend && npx --yes pnpm@10.7.0 install --frozen-lockfile \
                 && npx --yes pnpm@10.7.0 build)
fi

# --- Ключи -------------------------------------------------------------------
# Ключи Яндекса живут в .env (он в .gitignore). Сервис читает файл и сам,
# но здесь тоже подхватываем - тогда переменные видны и дочерним процессам.
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

if [ -z "${YANDEX_MAPS_API_KEY:-}" ]; then
  echo "Ключ Яндекс Карт не задан - карта будет собственной схемой."
  echo "Чтобы включить Яндекс Карты: cp .env.example .env и вписать ключ."
fi

echo "Интерфейс диспетчера: http://127.0.0.1:${PORT}"
exec "$VENV_PY" -m uvicorn dispatcher.api.app:app --host 127.0.0.1 --port "$PORT" --app-dir src
