"""Сборка сервиса: ручки, статика, запуск.

Рабочий день диспетчера живёт в `dispatcher.api.state`, ручки разложены по
смыслу в `dispatcher.api.routes`. Здесь только сборка и раздача интерфейса.
"""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.responses import FileResponse

from dispatcher.api import deps
from dispatcher.api.routes import datasets, manual, meta, planning, replanning, saving
from dispatcher.infrastructure import envfile
from dispatcher.services.scenario import load_all

HERE = os.path.dirname(os.path.abspath(__file__))
# Корень проекта лежит на три каталога выше: api -> dispatcher -> src -> корень.
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
RAW_DIR = os.path.join(ROOT, "data", "raw")
CACHE_PATH = os.path.join(ROOT, "data", "geo_cache.json")
FRONTEND_DIR = os.path.join(ROOT, "frontend")

# Ключ Яндекс Карт. Без него интерфейс рисует собственную схему и честно
# об этом сообщает. Как получить ключ, написано в README.
envfile.load()

app = FastAPI(title="Планировщик маршрутов выездных инженеров",
              version="1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")

for module in (meta, planning, replanning, manual, saving, datasets):
    app.include_router(module.router)


@app.on_event("startup")
def _startup() -> None:
    """Читает участки и готовит рабочий день."""
    deps.STORE.reset(load_all(RAW_DIR, CACHE_PATH))


def _static(name: str, media_type: str) -> FileResponse:
    return FileResponse(os.path.join(FRONTEND_DIR, name), media_type=media_type)


@app.get("/")
def index() -> FileResponse:
    return _static("index.html", "text/html")


@app.get("/app.js")
def app_js() -> FileResponse:
    return _static("app.js", "application/javascript")


@app.get("/map.js")
def map_js() -> FileResponse:
    return _static("map.js", "application/javascript")


@app.get("/styles.css")
def styles_css() -> FileResponse:
    return _static("styles.css", "text/css")
