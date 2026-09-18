"""Сборка сервиса: ручки, статика, запуск.

Рабочий день диспетчера живёт в `dispatcher.api.state`, ручки разложены по
смыслу в `dispatcher.api.routes`. Здесь только сборка и раздача интерфейса.
"""
from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from dispatcher.api import deps
from dispatcher.api.envelope import code_of, failed
from dispatcher.api.routes import datasets, manual, meta, planning, replanning, saving
from dispatcher.infrastructure import envfile
from dispatcher.services.scenario import load_all

HERE = os.path.dirname(os.path.abspath(__file__))
# Корень проекта лежит на три каталога выше: api -> dispatcher -> src -> корень.
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
RAW_DIR = os.path.join(ROOT, "data", "raw")
CACHE_PATH = os.path.join(ROOT, "data", "geo_cache.json")
FRONTEND_DIR = os.path.join(ROOT, "frontend")
DIST_DIR = os.path.join(FRONTEND_DIR, "dist")
# Витрина-прототип живёт рядом со сборкой нового интерфейса, пока тот
# не займёт её место целиком.
LEGACY_DIR = os.path.join(FRONTEND_DIR, "legacy")

# Ключ Яндекс Карт. Без него интерфейс рисует собственную схему и честно
# об этом сообщает. Как получить ключ, написано в README.
envfile.load()

app = FastAPI(title="Планировщик маршрутов выездных инженеров",
              version="1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")

for module in (meta, planning, replanning, manual, saving, datasets):
    app.include_router(module.router)


@app.exception_handler(HTTPException)
def _http_error(request: Request, error: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=error.status_code,
                        content=failed(code_of(error), str(error.detail)))


@app.exception_handler(RequestValidationError)
def _validation_error(request: Request,
                      error: RequestValidationError) -> JSONResponse:
    # Поля запроса собирает Pydantic, и его текст читать невозможно.
    # Диспетчеру достаточно знать, что запрос не принят. Статус остаётся
    # стандартным для непринятых полей, меняется только форма ответа.
    return JSONResponse(status_code=422, content=failed(
        "bad_request", "Запрос не принят: проверьте заполненные поля"))


@app.on_event("startup")
def _startup() -> None:
    """Читает участки и готовит рабочий день."""
    deps.STORE.reset(load_all(RAW_DIR, CACHE_PATH))


def _static(name: str, media_type: str) -> FileResponse:
    return FileResponse(os.path.join(LEGACY_DIR, name), media_type=media_type)


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


# Новый интерфейс собирается Vite и живёт на /ui, пока не заменит витрину.
# При разработке он поднимается своим сервером и ходит сюда через прокси.
if os.path.isdir(DIST_DIR):
    app.mount("/ui", StaticFiles(directory=DIST_DIR, html=True), name="ui")
