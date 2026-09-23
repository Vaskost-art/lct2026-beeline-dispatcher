"""Закрепление заявки за бригадой и смена её приоритета.

Обе правки меняют условия задачи, поэтому день пересчитывается целиком тем
же способом, каким был построен, с учётом отметок хода работ.
"""
from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter, HTTPException

from dispatcher.api.deps import STORE, scenario_of, version_of
from dispatcher.api.envelope import ok
from dispatcher.api.payload import plan_payload
from dispatcher.api.routes.planning import build_plan
from dispatcher.api.schemas import AdjustOrderRequest
from dispatcher.api.state import DayVersion
from dispatcher.services.metrics import plan_metrics
from dispatcher.services.planning.costs import DEFAULT_TIME_LIMIT_SEC
from dispatcher.services.planning.strategies import STRATEGIES
from dispatcher.services.statuses import settle_day

router = APIRouter()


# --- закрепление заявки и смена приоритета (ручные решения диспетчера) -------

@router.post("/api/order/adjust")
def adjust_order(request: AdjustOrderRequest) -> dict:
    """Закрепить заявку за бригадой и/или изменить её приоритет.

    Обе правки меняют условия задачи, поэтому план пересчитывается тем же
    способом, каким был построен. Предыдущее состояние уходит в историю:
    решение диспетчера всегда можно отменить.
    """
    scenario = scenario_of(request.region)
    revision = STORE.revision(request.region)
    state = version_of(request.region)
    orders, engineers = state.orders, state.engineers

    order = next((o for o in orders if o.id == request.order_id), None)
    if order is None:
        raise HTTPException(404, f"Заявка {request.order_id} не найдена")

    locked = dict(state.locked or {})
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
                missing = (f"навыка «{order.required_skill}»"
                           if order.required_skill not in target.skills
                           else f"транспорта «{order.required_vehicle}»")
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
        return ok(plan_payload(scenario, state.plan, state.metrics))

    # После события или ручной правки у плана стоит своя пометка
    # («replanned», «manual»), которой нет среди способов расчёта. Пересчёт в
    # таком случае идёт оптимизатором.
    strategy = state.plan.strategy if state.plan.strategy in STRATEGIES else "optimized"
    time_limit = request.time_limit_sec or DEFAULT_TIME_LIMIT_SEC
    solve_orders, crews, pinned = settle_day(state.plan, new_orders, engineers,
                                             locked, state.statuses)
    plan = build_plan(request.region, strategy, time_limit, solve_orders, crews, pinned)
    metrics = plan_metrics(plan, solve_orders, crews)

    STORE.push_since(revision, request.region, DayVersion(
        label=f"Заявка {request.order_id}: " + ", ".join(changes),
        plan=plan, metrics=metrics, orders=new_orders,
        engineers=crews, locked=locked, issued=state.issued,
        statuses=dict(state.statuses), manual=True))
    return ok(plan_payload(scenario, plan, metrics))
