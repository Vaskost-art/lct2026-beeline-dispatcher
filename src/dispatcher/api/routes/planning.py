"""Расчёт плана, сравнение вариантов, объяснения."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from dispatcher.api.deps import STORE, day, scenario_of, version_of
from dispatcher.api.payload import plan_payload
from dispatcher.api.schemas import ExplainRequest, PlanRequest
from dispatcher.api.state import DayVersion
from dispatcher.domain import Plan
from dispatcher.services.control import control_plan
from dispatcher.services.explain import explain_assignment
from dispatcher.services.metrics import compare, plan_metrics
from dispatcher.services.planning.costs import DEFAULT_TIME_LIMIT_SEC
from dispatcher.services.planning.strategies import (
    STRATEGIES,
    STRATEGY_FULL_TITLES,
    STRATEGY_HINTS,
    STRATEGY_TITLES,
)

router = APIRouter()


# --- планирование ------------------------------------------------------------

def build_plan(region: str, strategy: str, time_limit_sec: int,
                orders: list, engineers: list, locked: dict[str, str]) -> Plan:
    solver = STRATEGIES[strategy]
    if strategy == "optimized":
        return solver(orders, engineers, time_limit_sec=time_limit_sec,
                      locked=locked or None)
    return solver(orders, engineers, locked=locked or None)


@router.post("/api/plan")
def make_plan(request: PlanRequest) -> dict:
    scenario = scenario_of(request.region)
    previous = STORE.current(request.region)

    # Закрепления переживают пересчёт: диспетчер закрепил заявку за бригадой
    # не для одного варианта плана, а потому что так надо в этот день.
    # Сброс — отдельная кнопка, а не побочный эффект кнопки «Спланировать».
    locked = dict(previous.locked) if previous else {}
    orders = list(previous.orders) if previous else list(scenario.orders)
    engineers = list(previous.engineers) if previous else list(scenario.engineers)
    if request.reset:
        locked, orders, engineers = {}, list(scenario.orders), list(scenario.engineers)

    plan = build_plan(request.region, request.strategy, request.time_limit_sec,
                       orders, engineers, locked)

    metrics = plan_metrics(plan, orders, engineers)
    label = ("Сброс ручных правок" if request.reset else
             "Пересчёт: "
             f"{STRATEGY_TITLES.get(request.strategy, request.strategy).lower()}")
    # Пересчёт это тоже изменение: прежняя версия остаётся в истории, и к ней
    # диспетчер возвращается шагом назад, не пересчитывая заново.
    STORE.push(request.region, DayVersion(
        label=label, plan=plan, metrics=metrics,
        orders=orders, engineers=engineers, locked=locked))
    return plan_payload(scenario, plan, metrics)


@router.get("/api/plan/{region}")
def current_plan(region: str) -> dict:
    scenario = scenario_of(region)
    state = version_of(region)
    return plan_payload(scenario, state.plan, state.metrics)


@router.get("/api/compare/{region}")
def compare_strategies(region: str, time_limit_sec: int = DEFAULT_TIME_LIMIT_SEC) -> dict:
    """Сравнение всех вариантов плана и фактического распределения диспетчера.

    Сравнение всегда считается по исходному дню района, а не по текущему
    состоянию: факт диспетчера известен только для него, и подставлять
    в сравнение день, изменённый событиями, значило бы сопоставлять планы
    на разных наборах заявок. Об этом говорится в ответе полем `basis`.
    """
    scenario = scenario_of(region)
    changed = len(day(region).versions) > 1
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

@router.post("/api/explain")
def explain(request: ExplainRequest) -> dict:
    state = version_of(request.region)
    orders = state.orders
    order = next((o for o in orders if o.id == request.order_id), None)
    if order is None:
        raise HTTPException(404, f"Заявка {request.order_id} не найдена")
    return explain_assignment(order, state.plan, orders, state.engineers)
