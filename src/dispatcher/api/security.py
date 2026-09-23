"""Защита сервиса без входа: чужие сайты не пишут, чужие страницы не встраивают.

Входа нет по решению заказчика - диспетчер один. Поэтому любая открытая у
человека страница могла слать запросы на его локальный сервис: загрузка
набора принимала тело с любым типом, и чужой сайт подкладывал участки. Браузер
сам говорит, откуда запрос (`Sec-Fetch-Site`, `Origin`), - этого хватает.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from dispatcher.api.envelope import failed

#: Методы, которые ничего не меняют: их можно слать откуда угодно.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

#: Заголовки на каждый ответ. Встраивать интерфейс в чужую страницу нельзя:
#: кнопку «Применить к дню» можно было бы подсунуть под чужой клик.
HEADERS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
}


def _from_elsewhere(request: Request) -> bool:
    """Запрос пришёл с другого сайта."""
    site = request.headers.get("sec-fetch-site")
    if site is not None:
        return site == "cross-site"
    # Старые браузеры Sec-Fetch-Site не шлют: сверяем Origin с адресом сервиса.
    origin = request.headers.get("origin")
    if not origin:
        return False
    return urlsplit(origin).hostname != request.url.hostname


async def guard(request: Request,
                call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Отклоняет запись с чужих сайтов и ставит заголовки безопасности."""
    if request.method not in SAFE_METHODS and _from_elsewhere(request):
        return JSONResponse(status_code=403, content=failed(
            "forbidden", "Запрос с другого сайта отклонён"))
    response = await call_next(request)
    for name, value in HEADERS.items():
        response.headers.setdefault(name, value)
    return response
