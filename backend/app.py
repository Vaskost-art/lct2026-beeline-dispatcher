"""HTTP-API прототипа и раздача веб-интерфейса.

Состояние (текущий план по каждому району) держится в памяти процесса:
это учебный прототип для одного диспетчера, а не многопользовательская
система. Ограничение осознанное и описано в README.
"""
from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from typing import Any, Literal, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

import envfile
import geo
import norms
from domain import Plan, Route, hhmm, parse_hhmm
from explain import explain_assignment, explain_plan, explain_route
from dataset import (DatasetError, engineer_from_json, engineer_to_json,
                     load_upload, order_from_json, order_to_json,
                     scenario_from_json, scenario_to_json)
from ingest import REGIONS, Scenario, load_all
from metrics import compare, control_plan, plan_metrics
from risk import overrun_impact, plan_risk
from replan import (KIND_CANCEL, KIND_DELAYED, KIND_TITLES, KIND_UNAVAILABLE,
                    KIND_URGENT, MODE_FULL, MODE_HINTS, MODE_MINIMAL,
                    MODE_TITLES, ReplanEvent, make_urgent_order, replan)
from routing import evaluate_sequence
from solver import (DEFAULT_TIME_LIMIT_SEC, STRATEGIES, STRATEGY_FULL_TITLES,
                    STRATEGY_HINTS, STRATEGY_TITLES, diagnose, solve_optimized,
                    status_text)
from validate import validate

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RAW_DIR = os.path.join(ROOT, "data", "raw")
CACHE_PATH = os.path.join(ROOT, "data", "geo_cache.json")
FRONTEND_DIR = os.path.join(ROOT, "frontend")
SAVED_DIR = os.path.join(ROOT, "data", "saved")

# Сколько шагов назад можно отменить. Глубже диспетчеру не нужно, а память
# прототипа не резиновая: каждый шаг хранит полную копию плана.
HISTORY_LIMIT = 20

# Ключ Яндекс Карт. Без него интерфейс рисует собственную схему и честно
# об этом сообщает. Как получить ключ — написано в README.
envfile.load()
MAP_API_KEY = os.environ.get("YANDEX_MAPS_API_KEY", "").strip()

app = FastAPI(title="Планировщик маршрутов выездных инженеров",
              version="1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")

SCENARIOS: dict[str, Scenario] = {}
CURRENT: dict[str, dict[str, Any]] = {}      # region -> {plan, metrics, history}
DATASET_EVENTS: dict[str, list[dict]] = {}   # region -> события из набора данных


@app.on_event("startup")
def _startup() -> None:
    SCENARIOS.update(load_all(RAW_DIR, CACHE_PATH))


def _scenario(region: str) -> Scenario:
    scenario = SCENARIOS.get(region)
    if scenario is None:
        raise HTTPException(404, f"Район «{region}» не найден")
    return scenario


def _state(region: str) -> dict[str, Any]:
    state = CURRENT.get(region)
    if state is None:
        raise HTTPException(409, "План ещё не построен — сначала запустите планирование")
    return state


# --- история изменений: шаг назад (A30) --------------------------------------

def _snapshot(state: dict[str, Any], label: str) -> None:
    """Запоминает текущее состояние перед изменением.

    Копия полная: диспетчер должен иметь возможность вернуться ровно к тому
    плану, который он видел, а не к пересчитанному заново.
    """
    state.setdefault("history", []).append({
        "label": label,
        "plan": deepcopy(state["plan"]),
        "metrics": deepcopy(state["metrics"]),
        "orders": list(state["orders"]),
        "engineers": deepcopy(state["engineers"]),
        "locked": dict(state.get("locked") or {}),
    })
    if len(state["history"]) > HISTORY_LIMIT:
        del state["history"][0]


def _undo_labels(state: dict[str, Any]) -> list[str]:
    return [step["label"] for step in reversed(state.get("history") or [])]


# --- сериализация ------------------------------------------------------------

def _plan_payload(scenario: Scenario, plan: Plan, metrics: dict,
                  extra: dict | None = None) -> dict:
    by_id = scenario.order_by_id
    engineer_by_id = {e.id: e for e in _all_engineers(scenario)}
    # заявки, появившиеся после события, тоже должны попасть в ответ
    for route in plan.routes:
        for stop in route.stops:
            by_id.setdefault(stop.order_id, None)

    assignment: dict[str, str] = {}
    for route in plan.routes:
        for stop in route.stops:
            assignment[stop.order_id] = route.engineer_id

    payload = {
        "region": scenario.region_key,
        "region_name": scenario.region_name,
        "strategy": plan.strategy,
        "strategy_title": STRATEGY_TITLES.get(plan.strategy, plan.strategy),
        "solver_status": plan.solver_status,
        "solver_status_text": status_text(plan.solver_status),
        "solve_seconds": plan.solve_seconds,
        "locked": dict((CURRENT.get(scenario.region_key) or {}).get("locked") or {}),
        "undo": _undo_labels(CURRENT.get(scenario.region_key) or {}),
        "metrics": metrics,
        "explanation": explain_plan(plan, _all_orders(scenario, plan),
                                    _all_engineers(scenario), metrics),
        "engineers": [
            {**engineer.to_dict(),
             "used": any(r.engineer_id == engineer.id and r.is_used
                         for r in plan.routes)}
            for engineer in _all_engineers(scenario)
        ],
        "orders": [
            {**order.to_dict(), "assigned_to": assignment.get(order.id)}
            for order in _all_orders(scenario, plan)
        ],
        "routes": [route.to_dict() for route in plan.routes if route.is_used],
        "unassigned": [u.to_dict() for u in plan.unassigned],
        "route_summaries": [
            explain_route(engineer, plan, _all_orders(scenario, plan))
            for engineer in _all_engineers(scenario)
            if any(r.engineer_id == engineer.id and r.is_used for r in plan.routes)
        ],
        # прогноз опозданий считается вместе с планом: он дешёвый, а в
        # интерфейсе риск нужен сразу рядом с каждым визитом
        "risk": plan_risk(plan, _all_orders(scenario, plan), _all_engineers(scenario)),
        "geo": _geo_warning(_all_orders(scenario, plan)),
    }
    if extra:
        payload.update(extra)
    return payload


def _geo_warning(orders: list) -> dict:
    """Насколько можно доверять расстояниям в плане.

    Без прогона геокодера адрес разрешается в центроид района. Маршрут при
    этом остаётся корректным по навыкам, окнам и сменам, но километры и время
    в пути внутри района — оценка. Диспетчер должен видеть это до того,
    как отправит маршруты бригадам.
    """
    approx = [o.id for o in orders
              if getattr(o, "geocode_precision", "") == geo.PRECISION_APPROX]
    total = len(orders)
    share = len(approx) / total if total else 0.0
    if not approx:
        return {"approx_count": 0, "total": total, "share": 0.0,
                "level": "ok", "order_ids": [],
                "text": "Все адреса разрешены точно: расстояния и время в пути "
                        "посчитаны по реальным координатам."}
    return {
        "approx_count": len(approx),
        "total": total,
        "share": round(share, 3),
        # Пока точных координат меньше половины, километрам нельзя верить
        # даже приблизительно — это предупреждение, а не примечание.
        "level": "warn" if share >= 0.5 else "note",
        "order_ids": approx,
        "text": (f"У {len(approx)} из {total} заявок адрес не разрешён точно — "
                 f"взят центр района. Назначения, окна и смены от этого не "
                 f"страдают, но пробег и время в пути внутри района — оценка. "
                 f"Прогоните геокодер (scripts/geocode.py), чтобы цифры стали "
                 f"фактическими."),
    }


def _all_orders(scenario: Scenario, plan: Plan) -> list:
    """Заявки сценария плюс добавленные событиями переплана."""
    state = CURRENT.get(scenario.region_key)
    if state and state.get("orders"):
        return state["orders"]
    return scenario.orders


def _all_engineers(scenario: Scenario) -> list:
    """Исполнители рабочего дня, а не исходного сценария.

    События смещают смены: выбывшему бригадиру смена обрезается, остальным
    двигается начало. Ответ, собранный по исходному сценарию, показал бы
    прежние смены и посчитал бы по ним запас прочности.
    """
    state = CURRENT.get(scenario.region_key)
    if state and state.get("engineers"):
        return state["engineers"]
    return scenario.engineers


# --- модели запросов ---------------------------------------------------------

class PlanRequest(BaseModel):
    region: str
    strategy: Literal["baseline", "greedy", "optimized"] = "optimized"
    time_limit_sec: int = Field(DEFAULT_TIME_LIMIT_SEC, ge=1, le=120)
    # True — начать день с чистого листа: снять закрепления, вернуть исходные
    # заявки и смены. По умолчанию пересчёт сохраняет решения диспетчера.
    reset: bool = False


class ExplainRequest(BaseModel):
    region: str
    order_id: str


class NewOrderModel(BaseModel):
    id: str = "URGENT-1"
    lat: float
    lon: float
    address: str = "Адрес не указан"
    district: str = ""
    duration_min: int = Field(90, ge=5, le=480)
    window_start: str = "14:00"
    window_end: str = "16:00"
    required_skill: str = norms.SKILL_EMERGENCY
    required_vehicle: Optional[str] = None


class ReplanRequest(BaseModel):
    region: str
    kind: Literal["urgent_order", "cancel_order", "engineer_unavailable",
                  "engineer_delayed"]
    at: str = "13:00"
    order_id: Optional[str] = None
    engineer_id: Optional[str] = None
    delay_min: int = Field(45, ge=5, le=480)
    new_order: Optional[NewOrderModel] = None
    mode: Literal["minimal", "full"] = MODE_MINIMAL
    apply: bool = False
    time_limit_sec: int = Field(DEFAULT_TIME_LIMIT_SEC, ge=1, le=120)


class ReassignRequest(BaseModel):
    region: str
    order_id: str
    engineer_id: Optional[str] = None       # None = снять заявку с исполнителя


class AdjustOrderRequest(BaseModel):
    """Ручные правки диспетчера по одной заявке: закрепление и приоритет."""

    region: str
    order_id: str
    # "" или None — снять закрепление; иначе id исполнителя
    lock_to: Optional[str] = None
    set_lock: bool = False                  # трогать ли закрепление вообще
    priority: Optional[Literal["Обычная", "Срочная"]] = None
    time_limit_sec: int = Field(DEFAULT_TIME_LIMIT_SEC, ge=1, le=120)


class RegionRequest(BaseModel):
    region: str


class SavePlanRequest(BaseModel):
    region: str
    name: str = ""


# --- справочники и сценарии --------------------------------------------------

@app.get("/api/meta")
def meta() -> dict:
    return {
        "regions": [
            {**SCENARIOS[key].summary(),
             "builtin": key in REGIONS,
             "dataset_events": DATASET_EVENTS.get(key, [])}
            # сначала встроенные районы, затем загруженные пользователем
            for key in list(REGIONS) + [k for k in SCENARIOS if k not in REGIONS]
            if key in SCENARIOS
        ],
        "skills": list(norms.SKILL_BY_TYPE_BK.values()),
        "vehicles": list(norms.SPEED_KMH.keys()),
        "priorities": list(norms.PRIORITIES) if hasattr(norms, "PRIORITIES")
                      else [norms.PRIORITY_NORMAL, norms.PRIORITY_URGENT],
        "strategies": [{"key": k, "title": v,
                        "full_title": STRATEGY_FULL_TITLES.get(k, v),
                        "hint": STRATEGY_HINTS.get(k, "")}
                       for k, v in STRATEGY_TITLES.items()],
        "replan_kinds": [{"key": k, "title": v} for k, v in KIND_TITLES.items()],
        "replan_modes": [{"key": k, "title": v, "hint": MODE_HINTS.get(k, "")}
                         for k, v in MODE_TITLES.items()],
        "assumptions": [{"title": t, "text": x} for t, x in norms.ASSUMPTIONS],
        "map_api_key": MAP_API_KEY,
    }


@app.get("/api/scenario/{region}")
def scenario_info(region: str) -> dict:
    return _scenario(region).summary()


# --- планирование ------------------------------------------------------------

def _build_plan(region: str, strategy: str, time_limit_sec: int,
                orders: list, engineers: list, locked: dict[str, str]) -> Plan:
    solver = STRATEGIES[strategy]
    if strategy == "optimized":
        return solver(orders, engineers, time_limit_sec=time_limit_sec,
                      locked=locked or None)
    return solver(orders, engineers, locked=locked or None)


@app.post("/api/plan")
def make_plan(request: PlanRequest) -> dict:
    scenario = _scenario(request.region)
    previous = CURRENT.get(request.region)

    # Закрепления переживают пересчёт: диспетчер закрепил заявку за бригадой
    # не для одного варианта плана, а потому что так надо в этот день.
    # Сброс — отдельная кнопка, а не побочный эффект кнопки «Спланировать».
    locked = dict((previous or {}).get("locked") or {})
    orders = list((previous or {}).get("orders") or scenario.orders)
    engineers = list((previous or {}).get("engineers") or scenario.engineers)
    if request.reset:
        locked, orders, engineers = {}, list(scenario.orders), list(scenario.engineers)

    plan = _build_plan(request.region, request.strategy, request.time_limit_sec,
                       orders, engineers, locked)

    metrics = plan_metrics(plan, orders, engineers)
    state = {
        "plan": plan, "metrics": metrics, "orders": orders,
        "engineers": engineers, "locked": locked,
        "history": list((previous or {}).get("history") or []),
        "strategy": request.strategy, "time_limit_sec": request.time_limit_sec,
    }
    # Пересчёт — тоже изменение: к предыдущему плану диспетчер должен иметь
    # возможность вернуться, не пересчитывая его заново.
    if previous and previous.get("plan") is not None:
        state["history"].append({
            "label": "Сброс ручных правок" if request.reset else
                     f"Пересчёт: "
                     f"{STRATEGY_TITLES.get(request.strategy, request.strategy).lower()}",
            "plan": previous["plan"], "metrics": previous["metrics"],
            "orders": list(previous["orders"]),
            "engineers": list(previous["engineers"]),
            "locked": dict(previous.get("locked") or {}),
        })
        del state["history"][:-HISTORY_LIMIT]
    CURRENT[request.region] = state
    return _plan_payload(scenario, plan, metrics)


@app.get("/api/plan/{region}")
def current_plan(region: str) -> dict:
    scenario = _scenario(region)
    state = _state(region)
    return _plan_payload(scenario, state["plan"], state["metrics"])


@app.get("/api/compare/{region}")
def compare_strategies(region: str, time_limit_sec: int = DEFAULT_TIME_LIMIT_SEC) -> dict:
    """Сравнение всех вариантов плана и фактического распределения диспетчера.

    Сравнение всегда считается по исходному дню района, а не по текущему
    состоянию: факт диспетчера известен только для него, и подставлять
    в сравнение день, изменённый событиями, значило бы сопоставлять планы
    на разных наборах заявок. Об этом говорится в ответе полем `basis`.
    """
    scenario = _scenario(region)
    state = CURRENT.get(region) or {}
    changed = bool(state.get("history"))
    rows = []

    fact, fact_report = control_plan(scenario.orders, scenario.engineers)
    fact_metrics = plan_metrics(fact, scenario.orders, scenario.engineers)

    for key in ("baseline", "greedy", "optimized"):
        solver = STRATEGIES[key]
        plan = (solver(scenario.orders, scenario.engineers,
                       time_limit_sec=time_limit_sec) if key == "optimized"
                else solver(scenario.orders, scenario.engineers))
        metrics = plan_metrics(plan, scenario.orders, scenario.engineers)
        rows.append({"key": key, "title": STRATEGY_FULL_TITLES[key],
                     "hint": STRATEGY_HINTS[key], "metrics": metrics})

    optimized = next(r for r in rows if r["key"] == "optimized")
    baseline = next(r for r in rows if r["key"] == "baseline")

    return {
        "region": region,
        "region_name": scenario.region_name,
        "rows": rows,
        "fact": {"key": "control", "title": "Фактическое распределение диспетчера",
                 "metrics": fact_metrics, "report": fact_report},
        "vs_baseline": compare(optimized["metrics"], baseline["metrics"]),
        "vs_fact": compare(optimized["metrics"], fact_metrics),
        "basis": ("Сравнение посчитано по исходному дню района: в текущем плане "
                  "уже применены изменения, а факт диспетчера известен только "
                  "для исходного набора заявок."
                  if changed else
                  "Сравнение посчитано по тому же дню, что показан на экране."),
    }


# --- объяснения --------------------------------------------------------------

@app.post("/api/explain")
def explain(request: ExplainRequest) -> dict:
    scenario = _scenario(request.region)
    state = _state(request.region)
    orders = state["orders"]
    order = next((o for o in orders if o.id == request.order_id), None)
    if order is None:
        raise HTTPException(404, f"Заявка {request.order_id} не найдена")
    return explain_assignment(order, state["plan"], orders, state["engineers"])


# --- перепланирование --------------------------------------------------------

@app.post("/api/replan")
def do_replan(request: ReplanRequest) -> dict:
    scenario = _scenario(request.region)
    state = _state(request.region)
    orders, engineers = state["orders"], state["engineers"]

    try:
        at = parse_hhmm(request.at)
    except ValueError:
        raise HTTPException(400, "Время события должно быть в формате ЧЧ:ММ")

    new_order = None
    if request.kind == KIND_URGENT:
        if request.new_order is None:
            raise HTTPException(400, "Для срочной заявки нужен полный набор полей")
        payload = request.new_order
        if any(o.id == payload.id for o in orders):
            raise HTTPException(400, f"Заявка {payload.id} уже есть в плане")
        try:
            order_from_json({
                "id": payload.id, "lat": payload.lat, "lon": payload.lon,
                "address": payload.address, "district": payload.district,
                "duration_min": payload.duration_min,
                "window_start": payload.window_start,
                "window_end": payload.window_end,
                "priority": norms.PRIORITY_URGENT,
                "required_skill": payload.required_skill,
                "required_vehicle": payload.required_vehicle,
            })
        except DatasetError as exc:
            raise HTTPException(400, str(exc))

        new_order = make_urgent_order(
            order_id=payload.id, lat=payload.lat, lon=payload.lon,
            address=payload.address, district=payload.district,
            duration_min=payload.duration_min,
            window_start=parse_hhmm(payload.window_start),
            window_end=parse_hhmm(payload.window_end),
            required_skill=payload.required_skill,
            required_vehicle=payload.required_vehicle,
        )
    elif request.kind == KIND_CANCEL:
        if not request.order_id or not any(o.id == request.order_id for o in orders):
            raise HTTPException(400, "Укажите существующую заявку для отмены")
    elif request.kind in (KIND_UNAVAILABLE, KIND_DELAYED):
        if not request.engineer_id or not any(e.id == request.engineer_id
                                              for e in engineers):
            raise HTTPException(400, "Укажите существующего исполнителя")

    event = ReplanEvent(kind=request.kind, at=at, order_id=request.order_id,
                        engineer_id=request.engineer_id, new_order=new_order,
                        delay_min=request.delay_min)

    # Предпросмотр и применение обязаны показывать один и тот же план.
    # Поиск ограничен временем и второй запуск даёт другой результат, поэтому
    # применяем сохранённый вариант, а не считаем заново. Привязка к объекту
    # плана делает устаревший предпросмотр недействительным сама собой.
    signature = (request.kind, at, request.order_id, request.engineer_id,
                 request.delay_min, request.mode,
                 new_order.id if new_order is not None else None)
    preview = state.get("replan_preview")
    if (request.apply and preview
            and preview["signature"] == signature
            and preview["base"] is state["plan"]):
        result = preview["result"]
    else:
        result = replan(orders, engineers, state["plan"], event,
                        mode=request.mode,
                        time_limit_sec=request.time_limit_sec)
        if not request.apply:
            state["replan_preview"] = {"signature": signature,
                                       "base": state["plan"],
                                       "result": result}

    # Списки после события берём у самого переплана, а не пересобираем здесь:
    # событие может менять не только состав заявок, но и их поля (задержка
    # бригады удлиняет начатый визит), и вторая независимая сборка
    # разъезжается с планом — план перестаёт проходить проверку.
    new_orders = result.orders
    new_engineers = result.engineers

    metrics = plan_metrics(result.plan, new_orders, new_engineers)

    if request.apply:
        _snapshot(state, f"{KIND_TITLES.get(request.kind, request.kind)} "
                         f"в {hhmm(at)}")
        state["plan"] = result.plan
        state["metrics"] = metrics
        state["orders"] = new_orders
        # смены сдвинулись: остаток дня начинается с момента события,
        # у выбывшего исполнителя смена закрыта
        state["engineers"] = new_engineers
        state.pop("replan_preview", None)

    payload_scenario = scenario
    saved_orders = CURRENT[request.region]["orders"]
    CURRENT[request.region]["orders"] = new_orders
    try:
        payload = _plan_payload(payload_scenario, result.plan, metrics, extra={
            "diff": result.diff,
            "narrative": result.narrative,
            "applied": request.apply,
            "frozen": result.frozen,
        })
    finally:
        if not request.apply:
            CURRENT[request.region]["orders"] = saved_orders
    return payload


# --- ручное переназначение (дополнительная возможность из ТЗ) ----------------

@app.post("/api/reassign")
def reassign(request: ReassignRequest) -> dict:
    """Диспетчер вручную переносит заявку другому исполнителю."""
    scenario = _scenario(request.region)
    state = _state(request.region)
    orders, engineers = state["orders"], state["engineers"]
    plan: Plan = state["plan"]

    order = next((o for o in orders if o.id == request.order_id), None)
    if order is None:
        raise HTTPException(404, f"Заявка {request.order_id} не найдена")

    # Ручной перенос — это решение диспетчера, и оно должно пережить пересчёт.
    # Оставить закрепление на прежней бригаде значит вернуть заявку обратно при
    # первом же планировании и молча отменить то, что человек только что сделал.
    locked = state.setdefault("locked", {})
    if request.engineer_id:
        locked[request.order_id] = request.engineer_id
    else:
        locked.pop(request.order_id, None)

    by_id = {o.id: o for o in orders}
    engineer_by_id = {e.id: e for e in engineers}

    # снимаем заявку с текущего исполнителя
    sequences: dict[str, list] = {}
    for route in plan.routes:
        sequences[route.engineer_id] = [by_id[s.order_id] for s in route.stops
                                        if s.order_id != request.order_id]

    if request.engineer_id:
        target = engineer_by_id.get(request.engineer_id)
        if target is None:
            raise HTTPException(404, f"Исполнитель {request.engineer_id} не найден")
        if not target.can_do(order):
            missing = ("навыка «%s»" % order.required_skill
                       if order.required_skill not in target.skills
                       else "транспорта «%s»" % order.required_vehicle)
            raise HTTPException(400,
                                f"«{target.name}» не может взять эту заявку: нет {missing}")

        # ставим в позицию, которая даёт наименьший прирост пробега
        base = sequences.get(target.id, [])
        best = None
        for position in range(len(base) + 1):
            candidate = base[:position] + [order] + base[position:]
            route, reason = evaluate_sequence(target, candidate)
            if route is None:
                continue
            if best is None or route.total_km < best[0]:
                best = (route.total_km, candidate)
        if best is None:
            raise HTTPException(400,
                                f"«{target.name}» не успевает взять эту заявку: "
                                f"не выполняются окно {order.window_text} "
                                f"или смена {target.shift_text}")
        sequences[target.id] = best[1]

    routes = []
    for engineer in engineers:
        route, _ = evaluate_sequence(engineer, sequences.get(engineer.id, []))
        if route is None:
            raise HTTPException(400, f"Маршрут {engineer.name} стал невыполнимым")
        routes.append(route)

    new_plan = Plan(routes=routes, strategy="manual",
                    solver_status="MANUAL_REASSIGN")
    assigned = {s.order_id for r in new_plan.routes for s in r.stops}
    new_plan.unassigned = [diagnose(o, engineers) for o in orders
                           if o.id not in assigned]

    metrics = plan_metrics(new_plan, orders, engineers)
    _snapshot(state, f"Ручное назначение заявки {request.order_id}")
    state["plan"], state["metrics"] = new_plan, metrics
    return _plan_payload(scenario, new_plan, metrics)


# --- закрепление заявки и смена приоритета (ручные решения диспетчера) -------

@app.post("/api/order/adjust")
def adjust_order(request: AdjustOrderRequest) -> dict:
    """Закрепить заявку за бригадой и/или изменить её приоритет.

    Обе правки меняют условия задачи, поэтому план пересчитывается тем же
    способом, каким был построен. Предыдущее состояние уходит в историю:
    решение диспетчера всегда можно отменить.
    """
    scenario = _scenario(request.region)
    state = _state(request.region)
    orders, engineers = state["orders"], state["engineers"]

    order = next((o for o in orders if o.id == request.order_id), None)
    if order is None:
        raise HTTPException(404, f"Заявка {request.order_id} не найдена")

    locked = dict(state.get("locked") or {})
    changes: list[str] = []

    if request.set_lock:
        target_id = (request.lock_to or "").strip()
        if not target_id:
            if locked.pop(request.order_id, None) is not None:
                changes.append("закрепление снято")
        else:
            target = next((e for e in engineers if e.id == target_id), None)
            if target is None:
                raise HTTPException(404, f"Исполнитель {target_id} не найден")
            # Закреплять за тем, кто физически не может взять заявку, нельзя:
            # план стал бы заведомо невыполнимым, а диспетчер узнал бы об этом
            # только из пустого результата.
            if not target.can_do(order):
                missing = ("навыка «%s»" % order.required_skill
                           if order.required_skill not in target.skills
                           else "транспорта «%s»" % order.required_vehicle)
                raise HTTPException(
                    400, f"«{target.name}» не может взять эту заявку: нет {missing}")
            locked[request.order_id] = target_id
            changes.append(f"закреплена за «{target.name}»")

    new_orders = orders
    if request.priority and request.priority != order.priority:
        new_orders = [replace(o, priority=request.priority)
                      if o.id == request.order_id else o for o in orders]
        changes.append(f"приоритет «{request.priority}»")

    if not changes:
        return _plan_payload(scenario, state["plan"], state["metrics"])

    strategy = state.get("strategy", "optimized")
    time_limit = request.time_limit_sec or state.get("time_limit_sec",
                                                     DEFAULT_TIME_LIMIT_SEC)
    plan = _build_plan(request.region, strategy, time_limit,
                       new_orders, engineers, locked)
    metrics = plan_metrics(plan, new_orders, engineers)

    _snapshot(state, f"Заявка {request.order_id}: " + ", ".join(changes))
    state["plan"], state["metrics"] = plan, metrics
    state["orders"], state["locked"] = new_orders, locked
    return _plan_payload(scenario, plan, metrics)


# --- шаг назад (A30) ---------------------------------------------------------

@app.post("/api/undo")
def undo(request: RegionRequest) -> dict:
    """Возвращает план к состоянию до последнего изменения."""
    scenario = _scenario(request.region)
    state = _state(request.region)
    history = state.get("history") or []
    if not history:
        raise HTTPException(409, "Отменять нечего: план ещё не менялся")

    step = history.pop()
    state["plan"] = step["plan"]
    state["metrics"] = step["metrics"]
    state["orders"] = step["orders"]
    state["engineers"] = step["engineers"]
    state["locked"] = step["locked"]
    payload = _plan_payload(scenario, state["plan"], state["metrics"])
    payload["undone"] = step["label"]
    return payload


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


def _state_to_json(scenario: Scenario, state: dict[str, Any], name: str) -> dict:
    plan: Plan = state["plan"]
    return {
        "format": "dispatcher-saved-plan/1",
        "region": scenario.region_key,
        "region_name": scenario.region_name,
        "name": name or scenario.region_name,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "strategy": plan.strategy,
        "solver_status": plan.solver_status,
        "locked": dict(state.get("locked") or {}),
        "orders": [order_to_json(o) for o in state["orders"]],
        "engineers": [engineer_to_json(e) for e in state["engineers"]],
        # Маршруты храним последовательностями заявок, а не готовыми временами:
        # при загрузке они пересчитываются тем же кодом, что и в плане,
        # и любое расхождение вылезет сразу, а не тихо переживёт сохранение.
        "routes": [{"engineer": r.engineer_id,
                    "orders": [s.order_id for s in r.stops]}
                   for r in plan.routes if r.is_used],
    }


@app.post("/api/plan/save")
def save_plan(request: SavePlanRequest) -> dict:
    """Пишет текущий рабочий день на диск, чтобы он пережил перезапуск."""
    scenario = _scenario(request.region)
    state = _state(request.region)
    os.makedirs(SAVED_DIR, exist_ok=True)
    path = _saved_path(request.region)
    data = _state_to_json(scenario, state, request.name)
    # Пишем рядом и переименовываем: прямая запись усекает файл до того,
    # как в него лягут данные, и обрыв на этом месте стирает сохранённый день.
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return {"saved": True, "name": data["name"], "saved_at": data["saved_at"],
            "path": os.path.relpath(path, ROOT)}


@app.get("/api/plan/saved/{region}")
def saved_plan_info(region: str) -> dict:
    """Есть ли сохранённый день по этому району и когда он записан."""
    path = _saved_path(region)
    if not os.path.exists(path):
        return {"exists": False}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {"exists": False}
    return {"exists": True, "name": data.get("name", region),
            "saved_at": data.get("saved_at", ""),
            "orders": len(data.get("orders") or []),
            "strategy": data.get("strategy", "")}


@app.post("/api/plan/restore")
def restore_plan(request: RegionRequest) -> dict:
    """Поднимает сохранённый рабочий день и пересчитывает по нему маршруты."""
    path = _saved_path(request.region)
    # Загруженный набор живёт в памяти процесса и после перезапуска сервиса
    # не известен, а в файле сохранения лежит всё нужное, чтобы поднять район
    # заново. Иначе интерфейс предлагает «Восстановить» и получает 404.
    if request.region not in SCENARIOS and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                saved = json.load(fh)
            restored_scenario, _ = scenario_from_json(
                saved, region_key=request.region,
                region_name=saved.get("region_name") or request.region)
            SCENARIOS[request.region] = restored_scenario
        except (OSError, ValueError, DatasetError) as exc:
            raise HTTPException(400, f"Файл сохранения повреждён: {exc}")
    scenario = _scenario(request.region)
    if not os.path.exists(path):
        raise HTTPException(404, "Сохранённого плана для этого района нет")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise HTTPException(400, f"Файл сохранения повреждён: {exc}")

    try:
        orders = [order_from_json(o) for o in data.get("orders") or []]
        # У выбывшей за день бригады смена схлопнута в точку — это законное
        # состояние сохранённого дня, а не порча файла.
        engineers = [engineer_from_json(e, allow_empty_shift=True)
                     for e in data.get("engineers") or []]
    except DatasetError as exc:
        raise HTTPException(400, f"Файл сохранения повреждён: {exc}")

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

    CURRENT[request.region] = {
        "plan": plan, "metrics": metrics, "orders": orders,
        "engineers": engineers, "history": [],
        "locked": {k: v for k, v in (data.get("locked") or {}).items()
                   if k in by_id and v in engineer_by_id},
        "strategy": "optimized", "time_limit_sec": DEFAULT_TIME_LIMIT_SEC,
    }
    payload = _plan_payload(scenario, plan, metrics)
    payload["restored"] = {"name": data.get("name", request.region),
                           "saved_at": data.get("saved_at", ""),
                           "lost": lost}
    return payload


# --- загрузка и выгрузка набора данных (ТЗ п. 2.1) --------------------------

MAX_UPLOAD_BYTES = 8 * 1024 * 1024


def _free_region_key(base: str) -> str:
    """Подбирает свободный ключ, чтобы загрузка не затирала встроенные районы."""
    candidate = base or "upload"
    suffix = 2
    while candidate in SCENARIOS:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


@app.post("/api/dataset/upload")
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
        raise HTTPException(400, str(exc))

    if name.strip():
        scenario.region_name = name.strip()

    SCENARIOS[region_key] = scenario
    DATASET_EVENTS[region_key] = events
    CURRENT.pop(region_key, None)

    return {
        "region": region_key,
        "format": detected,
        "summary": scenario.summary(),
        "events": events,
    }


@app.get("/api/dataset/{region}")
def download_dataset(region: str) -> JSONResponse:
    """Отдаёт текущий набор данных района в JSON — формат для обратной загрузки."""
    scenario = _scenario(region)
    data = scenario_to_json(scenario, DATASET_EVENTS.get(region, []))
    return JSONResponse(content=data,
                        media_type="application/json; charset=utf-8")


@app.get("/api/risk/{region}")
def risk_report(region: str, overrun: int = 15) -> dict:
    """Прогноз опозданий: запас прочности маршрутов и последствия просадки."""
    _scenario(region)
    state = _state(region)
    overrun = max(0, min(int(overrun), 240))
    report = plan_risk(state["plan"], state["orders"], state["engineers"])
    report["custom_scenario"] = overrun_impact(
        state["plan"], state["orders"], state["engineers"], overrun)
    return report


@app.get("/api/validate/{region}")
def validate_plan(region: str) -> dict:
    """Независимая перепроверка текущего плана на соблюдение ограничений ТЗ."""
    _scenario(region)
    state = _state(region)
    report = validate(state["plan"], state["orders"], state["engineers"])
    return report.to_dict()


# --- выгрузка результата в формате ТЗ ---------------------------------------

@app.get("/api/export/{region}")
def export_plan(region: str) -> JSONResponse:
    """Результат в формате ТЗ п. 2.4.2 — для проверки и передачи дальше."""
    scenario = _scenario(region)
    state = _state(region)
    plan: Plan = state["plan"]
    orders = state["orders"]
    by_id = {o.id: o for o in orders}
    metrics = state["metrics"]

    assignment = {}
    for route in plan.routes:
        for stop in route.stops:
            assignment[stop.order_id] = route.engineer_id

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
            "пробег_по_исполнителям": {row["engineer_id"]: row["km"]
                                       for row in metrics["km_per_engineer"]},
            "суммарный_пробег_км": metrics["total_km"],
            "назначено_заявок": metrics["orders_assigned"],
            "всего_заявок": metrics["orders_total"],
        },
    }
    return JSONResponse(content=data, media_type="application/json; charset=utf-8")


# --- статика -----------------------------------------------------------------

if os.path.isdir(FRONTEND_DIR):

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

    @app.get("/app.js")
    def app_js() -> FileResponse:
        return FileResponse(os.path.join(FRONTEND_DIR, "app.js"),
                            media_type="application/javascript")

    @app.get("/map.js")
    def map_js() -> FileResponse:
        return FileResponse(os.path.join(FRONTEND_DIR, "map.js"),
                            media_type="application/javascript")

    @app.get("/styles.css")
    def styles() -> FileResponse:
        return FileResponse(os.path.join(FRONTEND_DIR, "styles.css"),
                            media_type="text/css")
