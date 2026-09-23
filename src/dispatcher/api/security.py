"""Защита сервиса без входа: чужие сайты не пишут и не читают, не встраивают.

Входа нет по решению заказчика - диспетчер один. Поэтому любая открытая у
человека страница могла слать запросы на его локальный сервис: подкладывать
участки, занимать расчёт картинкой на `/api/compare`, а после перепривязки
своего домена на 127.0.0.1 (DNS rebinding) и читать план с адресами. Браузер
сам говорит, откуда запрос (`Sec-Fetch-Site`, `Origin`), а имя в `Host`
выдаёт чужой домен.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from dispatcher.api.envelope import failed

log = logging.getLogger(__name__)

#: Методы, которые ничего не меняют.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

#: Имена, под которыми сервис открывают. Свои добавляются переменной
#: DISPATCHER_HOSTS через запятую; testserver - имя тестового клиента.
HOSTS = frozenset({"127.0.0.1", "localhost", "testserver"} | {
    name.strip() for name in os.environ.get("DISPATCHER_HOSTS", "").split(",")
    if name.strip()})

#: Предел тела обычной ручки. Загрузка набора держит свой предел сама.
MAX_BODY = 1024 * 1024

#: Заголовки на каждый ответ. Встраивать интерфейс в чужую страницу нельзя:
#: кнопку «Применить к дню» можно было бы подсунуть под чужой клик. Источник
#: страницы уходит к Яндексу, чтобы ключ карт можно было ограничить доменом.
HEADERS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


def _refused(request: Request) -> str:
    """Почему запрос отклоняется; пустая строка - пропустить."""
    if (request.url.hostname or "") not in HOSTS:
        return "Сервис открыт под чужим именем"
    if not request.url.path.startswith("/api/"):
        return ""
    # Другой порт этой же машины браузер считает same-site: это чужое
    # приложение, и ни читать, ни писать ему нельзя.
    site = request.headers.get("sec-fetch-site")
    if site is not None:
        return "" if site in ("same-origin", "none") else "Запрос с другого сайта отклонён"
    origin = request.headers.get("origin")
    if request.method in SAFE_METHODS or not origin:
        return ""
    # Старые браузеры Sec-Fetch-Site не шлют: сверяем источник целиком.
    parts = urlsplit(origin)
    same = (parts.scheme, parts.netloc) == (request.url.scheme, request.url.netloc)
    return "" if same else "Запрос с другого сайта отклонён"


def _too_big(request: Request) -> bool:
    declared = request.headers.get("content-length", "")
    return (declared.isdigit() and int(declared) > MAX_BODY
            and request.url.path != "/api/dataset/upload")


async def guard(request: Request,
                call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Отклоняет чужие запросы, ставит заголовки безопасности на любой ответ."""
    reason = _refused(request)
    if reason:
        response: Response = JSONResponse(status_code=403,
                                          content=failed("forbidden", reason))
    elif _too_big(request):
        response = JSONResponse(status_code=413, content=failed(
            "too_large", "Запрос слишком большой"))
    else:
        try:
            response = await call_next(request)
        except Exception:
            # Необработанный сбой отдаётся конвертом и с теми же заголовками,
            # а не голым «Internal Server Error» без защиты от встраивания.
            log.exception("необработанный сбой: %s %s", request.method, request.url.path)
            response = JSONResponse(status_code=500, content=failed(
                "internal", "Внутренняя ошибка сервиса, повторите действие"))
    for name, value in HEADERS.items():
        response.headers.setdefault(name, value)
    return response
