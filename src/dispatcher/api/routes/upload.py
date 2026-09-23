"""Приём набора данных: CSV выгрузки или JSON, как новый участок.

Ручка открыта всякому, кто достучался до сервиса, поэтому держит пределы:
размер тела, число заявок и бригад, число загруженных участков в памяти.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request

from dispatcher.api.deps import STORE
from dispatcher.api.envelope import ok
from dispatcher.api.paths import CACHE_PATH
from dispatcher.infrastructure.ingest import REGIONS
from dispatcher.services.dataset import DatasetError, load_upload

router = APIRouter()

MAX_UPLOAD_BYTES = 8 * 1024 * 1024

#: Сколько заявок и бригад принимает загрузка. Участки задачи - до 83 заявок
#: и 9 бригад; впятеро больше - запас, а не предел прототипа. Без потолка
#: набор на 3000 заявок держал процессор больше десяти минут.
MAX_ORDERS = 400
MAX_ENGINEERS = 60

#: Сколько загруженных участков держит память. Старший уходит первым;
#: встроенные участки задачи не вытесняются никогда.
MAX_UPLOADED = 10


async def _read_limited(request: Request) -> bytes:
    """Тело запроса с обрывом на пределе: целиком в память его не берём."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_UPLOAD_BYTES:
        raise _too_large()
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_UPLOAD_BYTES:
            raise _too_large()
        chunks.append(chunk)
    return b"".join(chunks)


def _too_large() -> HTTPException:
    return HTTPException(413, f"Файл больше {MAX_UPLOAD_BYTES // (1024 * 1024)} МБ: "
                              f"прототип рассчитан на один рабочий день участка")


def _free_region_key(base: str) -> str:
    """Подбирает свободный ключ, чтобы загрузка не затирала встроенные районы."""
    candidate = base or "upload"
    suffix = 2
    while STORE.has(candidate):
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


@router.post("/api/dataset/upload")
async def upload_dataset(request: Request, filename: str = "dataset",
                         name: str = "") -> dict:
    """Принимает набор данных в CSV или JSON и добавляет его как новый район."""
    raw = await _read_limited(request)
    if not raw:
        raise HTTPException(400, "Файл пустой - нечего загружать")

    stem = os.path.splitext(os.path.basename(filename))[0]
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in stem).strip("-")
    region_key = _free_region_key(safe.lower() or "upload")

    try:
        scenario, events, detected = load_upload(filename, raw, region_key, CACHE_PATH)
    except DatasetError as exc:
        raise HTTPException(400, str(exc)) from exc

    if len(scenario.orders) > MAX_ORDERS or len(scenario.engineers) > MAX_ENGINEERS:
        raise HTTPException(400, f"В наборе {len(scenario.orders)} заявок и "
                                 f"{len(scenario.engineers)} бригад, а прототип принимает "
                                 f"до {MAX_ORDERS} заявок и {MAX_ENGINEERS} бригад")
    if name.strip():
        scenario.region_name = name.strip()

    uploaded = [key for key in STORE.regions() if key not in REGIONS]
    for oldest in uploaded[:max(0, len(uploaded) - MAX_UPLOADED + 1)]:
        STORE.forget(oldest)
    STORE.replace_scenario(region_key, scenario, events)

    return ok({
        "region": region_key,
        "format": detected,
        "summary": scenario.summary(),
        "events": events,
    })
