"""Загрузка и выгрузка наборов данных."""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from dispatcher.api.deps import STORE, day, scenario_of, version_of
from dispatcher.api.envelope import ok
from dispatcher.api.paths import CACHE_PATH
from dispatcher.domain import Plan, hhmm
from dispatcher.services.dataset import DatasetError, load_upload, scenario_to_json
from dispatcher.services.impact import overrun_impact, plan_risk
from dispatcher.services.validate import validate

router = APIRouter()


# --- загрузка и выгрузка набора данных (ТЗ п. 2.1) --------------------------

MAX_UPLOAD_BYTES = 8 * 1024 * 1024


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
    raw = await request.body()
    if not raw:
        raise HTTPException(400, "Файл пустой — нечего загружать")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413, f"Файл больше {MAX_UPLOAD_BYTES // (1024 * 1024)} МБ. "
                 f"Прототип рассчитан на один рабочий день: "
                 f"10–15 инженеров и не более 100 заявок.")

    stem = os.path.splitext(os.path.basename(filename))[0]
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in stem).strip("-")
    region_key = _free_region_key(safe.lower() or "upload")

    try:
        scenario, events, detected = load_upload(filename, raw, region_key, CACHE_PATH)
    except DatasetError as exc:
        raise HTTPException(400, str(exc)) from exc

    if name.strip():
        scenario.region_name = name.strip()

    STORE.replace_scenario(region_key, scenario, events)

    return ok({
        "region": region_key,
        "format": detected,
        "summary": scenario.summary(),
        "events": events,
    })


@router.get("/api/dataset/{region}")
def download_dataset(region: str) -> JSONResponse:
    """Отдаёт текущий набор данных района в JSON — формат для обратной загрузки."""
    scenario = scenario_of(region)
    data = scenario_to_json(scenario, day(region).dataset_events)
    return JSONResponse(content=data,
                        media_type="application/json; charset=utf-8")


@router.get("/api/risk/{region}")
def risk_report(region: str, overrun: int = 15) -> dict:
    """Прогноз опозданий: запас прочности маршрутов и последствия просадки."""
    scenario_of(region)
    state = version_of(region)
    overrun = max(0, min(int(overrun), 240))
    report = plan_risk(state.plan, state.orders, state.engineers)
    report["custom_scenario"] = overrun_impact(
        state.plan, state.orders, state.engineers, overrun)
    return ok(report)


@router.get("/api/validate/{region}")
def validate_plan(region: str) -> dict:
    """Независимая перепроверка текущего плана на соблюдение ограничений ТЗ."""
    scenario_of(region)
    state = version_of(region)
    report = validate(state.plan, state.orders, state.engineers)
    payload = report.to_dict()
    # Правила проверяют то, что в плане. Заявки, которые в план не попали,
    # нарушением не являются, но зелёный ответ без их числа читается как
    # «весь день в порядке», хотя часть заявок сорвана.
    payload["orders_total"] = len(state.orders)
    payload["not_in_plan"] = len(state.orders) - report.checked_stops
    return ok(payload)


# --- выгрузка результата в формате ТЗ ---------------------------------------

@router.get("/api/export/{region}")
def export_plan(region: str) -> JSONResponse:
    """Результат в формате ТЗ п. 2.4.2 — для проверки и передачи дальше."""
    scenario = scenario_of(region)
    state = version_of(region)
    plan: Plan = state.plan
    orders = state.orders
    by_id = {o.id: o for o in orders}
    metrics = state.metrics

    assignment = {}
    for route in plan.routes:
        for stop in route.stops:
            assignment[stop.order_id] = route.engineer_id

    # Строки пробега разбираем до сборки ответа: так их тип виден проверке.
    km_rows = metrics["km_per_engineer"]
    per_engineer_km = {str(row["engineer_id"]): row["km"]
                       for row in (km_rows if isinstance(km_rows, list) else [])}

    data = {
        "район": scenario.region_name,
        "стратегия": plan.strategy,
        "исполнители": [
            {
                "исполнитель": route.engineer_id,
                "пробег_км": round(route.total_km, 2),
                "время_в_пути_мин": route.total_travel_min,
                "маршрут": [
                    {
                        "порядок": i + 1,
                        "заявка": stop.order_id,
                        "адрес": by_id[stop.order_id].address
                                 if stop.order_id in by_id else "",
                        "прибытие": hhmm(stop.arrival),
                        "начало_работ": hhmm(stop.start),
                        "окончание": hhmm(stop.end),
                        "пробег_до_точки_км": round(stop.travel_km, 2),
                    }
                    for i, stop in enumerate(route.stops)
                ],
            }
            for route in plan.routes if route.is_used
        ],
        "заявки": [
            {
                "заявка": order.id,
                "исполнитель": assignment.get(order.id),
                "статус": "назначена" if order.id in assignment else "не назначена",
            }
            for order in orders
        ],
        "не_назначены": [
            {"заявка": u.order_id, "причина": u.reason_text}
            for u in plan.unassigned
        ],
        "метрики": {
            "задействовано_исполнителей": metrics["used_engineers"],
            "доступно_исполнителей": metrics["engineers_available"],
            "пробег_по_исполнителям": per_engineer_km,
            "суммарный_пробег_км": metrics["total_km"],
            "назначено_заявок": metrics["orders_assigned"],
            "всего_заявок": metrics["orders_total"],
        },
    }
    return JSONResponse(content=data, media_type="application/json; charset=utf-8")
