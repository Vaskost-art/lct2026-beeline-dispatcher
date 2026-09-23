"""Сохранение и восстановление рабочего дня."""
from __future__ import annotations

import hashlib
import json
import os

from fastapi import APIRouter, HTTPException

from dispatcher.api.deps import STORE, scenario_of, version_of
from dispatcher.api.envelope import ok
from dispatcher.api.paths import ROOT, SAVED_DIR
from dispatcher.api.payload import plan_payload
from dispatcher.api.schemas import RegionRequest, SavePlanRequest
from dispatcher.api.state import DayVersion
from dispatcher.services.dataset import (
    DatasetError,
    rebuild,
    scenario_from_json,
    snapshot_from_json,
    snapshot_of,
    snapshot_to_json,
)

router = APIRouter()


# --- сохранение и восстановление рабочего дня (C10) --------------------------

def _why(error: Exception) -> str:
    """Причина для человека. Ошибка файловой системы печатает полный путь к
    файлу, а он раскрывает устройство машины - его наружу не отдаём."""
    return "файл не читается" if isinstance(error, OSError) else str(error)


def _saved_path(region: str) -> str:
    # Имя файла собираем сами из ключа района: подставленный путь не должен
    # уводить запись за пределы каталога.
    safe = "".join(ch for ch in region if ch.isalnum() or ch in "-_")
    if not safe:
        raise HTTPException(400, "Недопустимое имя района")
    if len(safe) > 48:
        # Обрезка длинного ключа сводила разные районы в один файл, и день
        # одного района восстанавливался под именем другого.
        digest = hashlib.sha256(region.encode("utf-8")).hexdigest()[:12]
        safe = f"{safe[:48]}-{digest}"
    return os.path.join(SAVED_DIR, f"{safe}.json")


@router.post("/api/plan/save")
def save_plan(request: SavePlanRequest) -> dict:
    """Пишет текущий рабочий день на диск, чтобы он пережил перезапуск."""
    scenario = scenario_of(request.region)
    state = version_of(request.region)
    os.makedirs(SAVED_DIR, exist_ok=True)
    path = _saved_path(request.region)
    data = snapshot_to_json(snapshot_of(
        scenario.region_key, scenario.region_name, state.label, state.plan,
        state.orders, state.engineers, state.locked, state.manual,
        name=request.name, issued=state.issued, statuses=state.statuses))
    # Пишем рядом и переименовываем: прямая запись усекает файл до того,
    # как в него лягут данные, и обрыв на этом месте стирает сохранённый день.
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return ok({"saved": True, "name": data["name"], "saved_at": data["saved_at"],
            "path": os.path.relpath(path, ROOT)})


@router.get("/api/plan/saved/{region}")
def saved_plan_info(region: str) -> dict:
    """Есть ли сохранённый день по этому району и когда он записан."""
    path = _saved_path(region)
    if not os.path.exists(path):
        return ok({"exists": False})
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return ok({"exists": False})
    return ok({"exists": True, "name": data.get("name", region),
            "saved_at": data.get("saved_at", ""),
            "orders": len(data.get("orders") or []),
            "strategy": data.get("strategy", "")})


@router.post("/api/plan/restore")
def restore_plan(request: RegionRequest) -> dict:
    """Поднимает сохранённый рабочий день и пересчитывает по нему маршруты."""
    path = _saved_path(request.region)
    # Загруженный набор живёт в памяти процесса и после перезапуска сервиса
    # не известен, а в файле сохранения лежит всё нужное, чтобы поднять район
    # заново. Иначе интерфейс предлагает «Восстановить» и получает 404.
    if not STORE.has(request.region) and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                saved = json.load(fh)
            restored_scenario, _ = scenario_from_json(
                saved, region_key=request.region,
                region_name=saved.get("region_name") or request.region)
            STORE.replace_scenario(request.region, restored_scenario)
        except (OSError, ValueError, DatasetError) as exc:
            raise HTTPException(400, f"Файл сохранения повреждён: {_why(exc)}") from exc
    scenario = scenario_of(request.region)
    revision = STORE.revision(request.region)
    if not os.path.exists(path):
        raise HTTPException(404, "Сохранённого плана для этого района нет")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise HTTPException(400, f"Файл сохранения повреждён: {_why(exc)}") from exc

    # Разбор и подъём маршрутов общие с журналом дня: день, поднятый из файла,
    # не должен отличаться от поднятого из базы.
    try:
        snapshot = snapshot_from_json(data)
        plan, metrics, lost = rebuild(snapshot)
    except DatasetError as exc:
        raise HTTPException(400, f"Файл сохранения повреждён: {exc}") from exc

    STORE.push_since(revision, request.region, DayVersion(
        label="Восстановлен сохранённый день",
        plan=plan, metrics=metrics, orders=snapshot.orders,
        engineers=snapshot.engineers, locked=snapshot.locked,
        issued=snapshot.issued, statuses=snapshot.statuses, manual=True))
    payload = plan_payload(scenario, plan, metrics)
    payload["restored"] = {"name": snapshot.name or request.region,
                           "saved_at": snapshot.saved_at, "lost": lost}
    return ok(payload)
