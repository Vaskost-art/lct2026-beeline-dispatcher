"""Формат ответа сервиса.

Один вид у всех ручек: либо `{"ok": true, "data": ...}`, либо
`{"ok": false, "error": {"code", "message"}}`. Код машиночитаемый и нужен
экрану для развилки, сообщение это готовый текст для человека.
"""
from __future__ import annotations

from fastapi import HTTPException

#: Код по умолчанию для ошибок, у которых своего кода нет.
BY_STATUS = {
    400: "bad_request",
    404: "not_found",
    409: "conflict",
    413: "too_large",
    422: "bad_request",
}


class ApiError(HTTPException):
    """Ошибка с машиночитаемым кодом."""

    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(status_code=status, detail=message)
        self.code = code


def ok(data: object) -> dict[str, object]:
    """Удачный ответ."""
    return {"ok": True, "data": data}


def failed(code: str, message: str) -> dict[str, object]:
    """Неудачный ответ."""
    return {"ok": False, "error": {"code": code, "message": message}}


def code_of(error: HTTPException) -> str:
    """Код ошибки: свой, если задан, иначе выведенный из статуса."""
    own = getattr(error, "code", "")
    return str(own) if own else BY_STATUS.get(error.status_code, "error")
