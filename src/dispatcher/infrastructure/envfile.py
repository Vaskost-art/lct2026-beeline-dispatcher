"""Чтение файла .env.

Ключи Яндекса нельзя ни коммитить, ни просить набирать `export` каждый раз
перед запуском. Поэтому рядом с проектом лежит .env (он в .gitignore), и мы
подгружаем его при старте: и сервис, и скрипты берут ключи оттуда.

Формат самый простой: `КЛЮЧ=значение`, по строке на ключ, комментарии с `#`.
Внешнее окружение всегда сильнее файла — переменная, заданная в оболочке или
в docker-compose, не перетирается.
"""
from __future__ import annotations

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATH = os.path.join(ROOT, ".env")


def load(path: str = DEFAULT_PATH) -> dict[str, str]:
    """Подгружает .env в окружение процесса. Возвращает то, что подставил."""
    if not os.path.exists(path):
        return {}

    applied: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        # Нечитаемый .env не должен ронять запуск: без ключей сервис работает,
        # просто рисует собственную схему вместо Яндекс Карт.
        return {}

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        # `export КЛЮЧ=значение` — привычная форма, принимаем и её
        if name.startswith("export "):
            name = name[len("export "):].strip()
        value = value.strip().strip('"').strip("'")
        if not name or name in os.environ:
            continue
        os.environ[name] = value
        applied[name] = value
    return applied
