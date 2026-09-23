"""Ручные решения диспетчера: перенос заявки и шаг назад.

Закрепление и смена приоритета - в `adjust.py`.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from dispatcher.api.deps import STORE, scenario_of, version_of
from dispatcher.api.envelope import ok
from dispatcher.api.payload import plan_payload
from dispatcher.api.schemas import ReassignRequest, RegionRequest
from dispatcher.api.state import DayVersion
from dispatcher.domain import Plan
from dispatcher.services.equipment import missing_for, name_listing
from dispatcher.services.metrics import plan_metrics
from dispatcher.services.planning.reasons import diagnose
from dispatcher.services.routing import evaluate_sequence
from dispatcher.services.statuses import is_closed, is_started, status_of

router = APIRouter()


# --- ручное переназначение (дополнительная возможность из ТЗ) ----------------

@router.post("/api/reassign")
def reassign(request: ReassignRequest) -> dict:
    """Диспетчер вручную переносит заявку другому исполнителю."""
    scenario = scenario_of(request.region)
    revision = STORE.revision(request.region)
    state = version_of(request.region)
    orders, engineers = state.orders, state.engineers
    plan: Plan = state.plan

    order = next((o for o in orders if o.id == request.order_id), None)
    if order is None:
        raise HTTPException(404, f"Заявка {request.order_id} не найдена")

    # Заявку, которую бригада уже делает или закрыла, переносить поздно:
    # работа либо идёт, либо закончена, и план обязан это отражать.
    mark = status_of(request.order_id, state.statuses)
    if is_started(request.order_id, state.statuses) or is_closed(
            request.order_id, state.statuses):
        raise HTTPException(
            400, f"Заявка {request.order_id} уже в состоянии «{mark}»: "
                 f"переносить её поздно")

    # Ручной перенос - это решение диспетчера, и оно должно пережить пересчёт.
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

        # Оборудование бригада получила утром на весь день: заявку под то,
        # чего у неё с собой нет, она физически не выполнит.
        short = missing_for(order, target.id, state.issued, plan, orders)
        if short:
            raise HTTPException(
                400, f"«{target.name}» не может взять эту заявку: с собой нет "
                     f"{name_listing(short)}. Устройство может передать другая "
                     f"бригада: «Что взять в офисе», блок передачи")

        # ставим в позицию, которая даёт наименьший прирост пробега
        base = sequences.get(target.id, [])
        best = None
        for position in range(len(base) + 1):
            candidate = base[:position] + [order] + base[position:]
            built, reason = evaluate_sequence(target, candidate)
            if built is None:
                continue
            if best is None or built.total_km < best[0]:
                best = (built.total_km, candidate)
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
    STORE.push_since(revision, request.region, DayVersion(
        label=f"Ручное назначение заявки {request.order_id}",
        plan=new_plan, metrics=metrics, orders=list(orders),
        engineers=list(engineers), locked=locked, issued=state.issued,
        statuses=dict(state.statuses), manual=True))
    return ok(plan_payload(scenario, new_plan, metrics))


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
    return ok(payload)
