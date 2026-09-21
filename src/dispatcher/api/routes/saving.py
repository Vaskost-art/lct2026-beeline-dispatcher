"""Сохранение и восстановление рабочего дня."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime

from fastapi import APIRouter, HTTPException

from dispatcher.api.deps import STORE, scenario_of, version_of
from dispatcher.api.envelope import ok
from dispatcher.api.paths import ROOT, SAVED_DIR
from dispatcher.api.payload import plan_payload
from dispatcher.api.schemas import RegionRequest, SavePlanRequest
from dispatcher.api.state import DayVersion
from dispatcher.domain import Plan, Route
from dispatcher.domain.scenario import Scenario
from dispatcher.services.dataset import (
    DatasetError,
    engineer_from_json,
    engineer_to_json,
    order_from_json,
    order_to_json,
    scenario_from_json,
)
from dispatcher.services.metrics import plan_metrics
from dispatcher.services.planning.reasons import diagnose
from dispatcher.services.routing import evaluate_sequence

router = APIRouter()


# --- сохранение и восстановление рабочего дня (C10) --------------------------

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


def _state_to_json(scenario: Scenario, state: DayVersion, name: str) -> dict:
    plan: Plan = state.plan
    return {
        "format": "dispatcher-saved-plan/1",
        "region": scenario.region_key,
        "region_name": scenario.region_name,
        "name": name or scenario.region_name,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "strategy": plan.strategy,
        "solver_status": plan.solver_status,
        "locked": dict(state.locked or {}),
        "orders": [order_to_json(o) for o in state.orders],
        "engineers": [engineer_to_json(e) for e in state.engineers],
        # Маршруты храним последовательностями заявок, а не готовыми временами:
        # при загрузке они пересчитываются тем же кодом, что и в плане,
        # и любое расхождение вылезет сразу, а не тихо переживёт сохранение.
        "routes": [{"engineer": r.engineer_id,
                    "orders": [s.order_id for s in r.stops]}
                   for r in plan.routes if r.is_used],
    }


@router.post("/api/plan/save")
def save_plan(request: SavePlanRequest) -> dict:
    """Пишет текущий рабочий день на диск, чтобы он пережил перезапуск."""
    scenario = scenario_of(request.region)
    state = version_of(request.region)
    os.makedirs(SAVED_DIR, exist_ok=True)
    path = _saved_path(request.region)
    data = _state_to_json(scenario, state, request.name)
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
            raise HTTPException(400, f"Файл сохранения повреждён: {exc}") from exc
    scenario = scenario_of(request.region)
    if not os.path.exists(path):
        raise HTTPException(404, "Сохранённого плана для этого района нет")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise HTTPException(400, f"Файл сохранения повреждён: {exc}") from exc

    try:
        orders = [order_from_json(o) for o in data.get("orders") or []]
        # У выбывшей за день бригады смена схлопнута в точку — это законное
        # состояние сохранённого дня, а не порча файла.
        engineers = [engineer_from_json(e, allow_empty_shift=True)
                     for e in data.get("engineers") or []]
    except DatasetError as exc:
        raise HTTPException(400, f"Файл сохранения повреждён: {exc}") from exc

    by_id = {o.id: o for o in orders}
    engineer_by_id = {e.id: e for e in engineers}
    routes = []
    lost: list[str] = []
    for saved_route in data.get("routes") or []:
        engineer = engineer_by_id.get(saved_route.get("engineer"))
        if engineer is None:
            continue
        sequence = [by_id[oid] for oid in saved_route.get("orders") or []
                    if oid in by_id]
        route, _ = evaluate_sequence(engineer, sequence)
        if route is None:
            # Данные в файле разошлись с правилами — не поднимаем битый план
            # молча, а говорим, чей маршрут не сходится.
            raise HTTPException(
                400, f"Сохранённый маршрут «{engineer.name}» не проходит "
                     f"проверку ограничений — файл не соответствует данным")
        if len(route.stops) != len(saved_route.get("orders") or []):
            lost.extend(oid for oid in saved_route.get("orders") or []
                        if oid not in by_id)
        routes.append(route)

    covered = {r.engineer_id for r in routes}
    routes.extend(Route(engineer_id=e.id) for e in engineers
                  if e.id not in covered)

    plan = Plan(routes=routes, strategy=data.get("strategy", "restored"),
                solver_status="RESTORED")
    assigned = {s.order_id for r in plan.routes for s in r.stops}
    plan.unassigned = [diagnose(o, engineers) for o in orders
                       if o.id not in assigned]
    metrics = plan_metrics(plan, orders, engineers)

    STORE.push(request.region, DayVersion(
        label="Восстановлен сохранённый день",
        plan=plan, metrics=metrics, orders=orders, engineers=engineers,
        locked={k: v for k, v in (data.get("locked") or {}).items()
                if k in by_id and v in engineer_by_id},
        manual=True))
    payload = plan_payload(scenario, plan, metrics)
    payload["restored"] = {"name": data.get("name", request.region),
                           "saved_at": data.get("saved_at", ""),
                           "lost": lost}
    return ok(payload)
