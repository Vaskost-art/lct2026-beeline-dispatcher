"""Пути к данным и ключ карты: одно объявление на весь сервис."""
from __future__ import annotations

import os

from dispatcher.infrastructure import envfile

HERE = os.path.dirname(os.path.abspath(__file__))
#: Корень проекта: api -> dispatcher -> src -> корень.
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
RAW_DIR = os.path.join(ROOT, "data", "raw")
CACHE_PATH = os.path.join(ROOT, "data", "geo_cache.json")
FRONTEND_DIR = os.path.join(ROOT, "frontend")
SAVED_DIR = os.path.join(ROOT, "data", "saved")

envfile.load()
#: Без ключа интерфейс рисует собственную схему и честно об этом говорит.
MAP_API_KEY = os.environ.get("YANDEX_MAPS_API_KEY", "").strip()
