"""Расчёт плана, сравнение вариантов, объяснения."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from dispatcher.api.deps import STORE, day, scenario_of, version_of
from dispatcher.api.envelope import ok
from dispatcher.api.payload import plan_payload
from dispatcher.api.schemas import ExplainRequest, PlanRequest
from dispatcher.api.state import DayVersion
from dispatcher.domain import Engineer, Order, Plan
from dispatcher.services.control import control_plan
from dispatcher.services.equipment import issued_items
from dispatcher.services.explain import explain_assignment
from dispatcher.services.metrics import compare, plan_metrics
from dispatcher.services.planning.baseline import solve_baseline, solve_greedy
from dispatcher.services.planning.costs import DEFAULT_TIME_LIMIT_SEC
from dispatcher.services.planning.optimizer import solve_optimized
from dispatcher.services.planning.strategies import (
    STRATEGY_FULL_TITLES,
    STRATEGY_HINTS,
    STRATEGY_METHODS,
    STRATEGY_TITLES,
)

router = APIRouter()


# --- планирование ------------------------------------------------------------

def build_plan(region: str, strategy: str, time_limit_sec: int,
               orders: list[Order], engineers: list[Engineer],
               locked: dict[str, str]) -> Plan:
    """Строит план выбранным способом."""
    if strategy == "optimized":
        return solve_optimized(orders, engineers, time_limit_sec=time_limit_sec,
                               locked=locked or None)
    if strategy == "baseline":
        return solve_baseline(orders, engineers, locked=locked or None)
    return solve_greedy(orders, engineers, locked=locked or None)


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
    # Оборудование выдаётся в офисе один раз, по первому плану дня: бригада
    # уехала с этой сумкой, и пересчёт её не пополняет. Сброс дня начинает
    # утро заново, поэтому выдача считается снова.
    issued = {} if (previous is None or request.reset) else dict(previous.issued)
    if not issued:
        issued = issued_items(plan, orders)
    label = ("Сброс ручных правок" if request.reset else
             "Пересчёт: "
             f"{STRATEGY_TITLES.get(request.strategy, request.strategy).lower()}")
    # Пересчёт это тоже изменение: прежняя версия остаётся в истории, и к ней
    # диспетчер возвращается шагом назад, не пересчитывая заново.
    STORE.push(request.region, DayVersion(
        label=label, plan=plan, metrics=metrics, orders=orders,
        engineers=engineers, locked=locked, issued=issued,
        statuses=dict(previous.statuses) if previous and not request.reset else {}))
    return ok(plan_payload(scenario, plan, metrics))


@router.get("/api/plan/{region}")
def current_plan(region: str) -> dict:
    scenario = scenario_of(region)
    state = version_of(region)
    return ok(plan_payload(scenario, state.plan, state.metrics))


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

    by_key: dict[str, dict[str, float]] = {}
    for key in ("baseline", "greedy", "optimized"):
        plan = build_plan(region, key, time_limit_sec,
                          scenario.orders, scenario.engineers, {})
        metrics = plan_metrics(plan, scenario.orders, scenario.engineers)
        by_key[key] = metrics
        rows.append({"key": key, "title": STRATEGY_FULL_TITLES[key],
                     "method": STRATEGY_METHODS[key],
                     "hint": STRATEGY_HINTS[key], "metrics": metrics})

    return ok({
        "region": region,
        "region_name": scenario.region_name,
        "rows": rows,
        "changed": changed,
        "fact": {"key": "control", "title": "Фактическое распределение диспетчера",
                 "metrics": fact_metrics, "report": fact_report},
        "vs_baseline": compare(by_key["optimized"], by_key["baseline"]),
        "vs_fact": compare(by_key["optimized"], fact_metrics),
        "basis": ("Сравнение посчитано по исходному дню участка: в текущем плане "
                  "уже применены изменения, и сопоставлять способы расчёта на "
                  "разных наборах заявок было бы неверно."
                  if changed else
                  "Сравнение посчитано по тому же дню, что показан на экране."),
    })


# --- объяснения --------------------------------------------------------------

@router.post("/api/explain")
def explain(request: ExplainRequest) -> dict:
    state = version_of(request.region)
    orders = state.orders
    order = next((o for o in orders if o.id == request.order_id), None)
    if order is None:
        raise HTTPException(404, f"Заявка {request.order_id} не найдена")
    return ok(explain_assignment(order, state.plan, orders, state.engineers))
