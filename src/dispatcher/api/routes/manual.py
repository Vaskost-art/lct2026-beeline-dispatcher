"""Ручные решения диспетчера: перенос, закрепление, шаг назад."""
from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter, HTTPException

from dispatcher.api.deps import STORE, scenario_of, version_of
from dispatcher.api.payload import plan_payload
from dispatcher.api.routes.planning import build_plan
from dispatcher.api.schemas import AdjustOrderRequest, ReassignRequest, RegionRequest
from dispatcher.api.state import DayVersion
from dispatcher.domain import Plan
from dispatcher.services.metrics import plan_metrics
from dispatcher.services.planning.costs import DEFAULT_TIME_LIMIT_SEC
from dispatcher.services.planning.reasons import diagnose
from dispatcher.services.planning.strategies import STRATEGIES
from dispatcher.services.routing import evaluate_sequence

router = APIRouter()


# --- ручное переназначение (дополнительная возможность из ТЗ) ----------------

@router.post("/api/reassign")
def reassign(request: ReassignRequest) -> dict:
    """Диспетчер вручную переносит заявку другому исполнителю."""
    scenario = scenario_of(request.region)
    state = version_of(request.region)
    orders, engineers = state.orders, state.engineers
    plan: Plan = state.plan

    order = next((o for o in orders if o.id == request.order_id), None)
    if order is None:
        raise HTTPException(404, f"Заявка {request.order_id} не найдена")

    # Ручной перенос — это решение диспетчера, и оно должно пережить пересчёт.
    # Оставить закрепление на прежней бригаде значит вернуть заявку обратно при
    # первом же планировании и молча отменить то, что человек только что сделал.
    locked = dict(state.locked)
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
            missing = (f"навыка «{order.required_skill}»"
                       if order.required_skill not in target.skills
                       else f"транспорта «{order.required_vehicle}»")
            raise HTTPException(
                400, f"«{target.name}» не может взять эту заявку: нет {missing}")

        # ставим в позицию, которая даёт наименьший прирост пробега
        base = sequences.get(target.id, [])
        best = None
        for position in range(len(base) + 1):
            candidate = base[:position] + [order] + base[position:]
            built, reason = evaluate_sequence(target, candidate)
            if built is None:
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
        built, _ = evaluate_sequence(engineer, sequences.get(engineer.id, []))
        if built is None:
            raise HTTPException(400, f"Маршрут {engineer.name} стал невыполнимым")
        routes.append(built)

    new_plan = Plan(routes=routes, strategy="manual",
                    solver_status="MANUAL_REASSIGN")
    assigned = {s.order_id for r in new_plan.routes for s in r.stops}
    new_plan.unassigned = [diagnose(o, engineers) for o in orders
                           if o.id not in assigned]

    metrics = plan_metrics(new_plan, orders, engineers)
    STORE.push(request.region, DayVersion(
        label=f"Ручное назначение заявки {request.order_id}",
        plan=new_plan, metrics=metrics, orders=list(orders),
        engineers=list(engineers), locked=locked))
    return plan_payload(scenario, new_plan, metrics)


# --- закрепление заявки и смена приоритета (ручные решения диспетчера) -------

@router.post("/api/order/adjust")
def adjust_order(request: AdjustOrderRequest) -> dict:
    """Закрепить заявку за бригадой и/или изменить её приоритет.

    Обе правки меняют условия задачи, поэтому план пересчитывается тем же
    способом, каким был построен. Предыдущее состояние уходит в историю:
    решение диспетчера всегда можно отменить.
    """
    scenario = scenario_of(request.region)
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
        return plan_payload(scenario, state.plan, state.metrics)

    # После события или ручной правки у плана стоит своя пометка
    # («replanned», «manual»), которой нет среди способов расчёта. Пересчёт в
    # таком случае идёт оптимизатором.
    strategy = state.plan.strategy if state.plan.strategy in STRATEGIES else "optimized"
    time_limit = request.time_limit_sec or DEFAULT_TIME_LIMIT_SEC
    plan = build_plan(request.region, strategy, time_limit,
                       new_orders, engineers, locked)
    metrics = plan_metrics(plan, new_orders, engineers)

    STORE.push(request.region, DayVersion(
        label=f"Заявка {request.order_id}: " + ", ".join(changes),
        plan=plan, metrics=metrics, orders=new_orders,
        engineers=list(engineers), locked=locked))
    return plan_payload(scenario, plan, metrics)


# --- шаг назад (A30) ---------------------------------------------------------

@router.post("/api/undo")
def undo(request: RegionRequest) -> dict:
    """Возвращает план к состоянию до последнего изменения."""
    scenario = scenario_of(request.region)
    undone = version_of(request.region).label
    previous = STORE.step_back(request.region)
    if previous is None:
        raise HTTPException(409, "Отменять нечего: план ещё не менялся")

    payload = plan_payload(scenario, previous.plan, previous.metrics)
    payload["undone"] = undone
    return payload
