"""Ход смены: диспетчер отмечает, что с заявкой происходит сейчас.

Организаторы: факт выполнения или отмены фиксирует диспетчер на основании
информации от бригады; закрытые заявки в дальнейшее планирование не
включаются. Отметка - это решение человека, поэтому она ложится новой
версией дня и отменяется шагом назад.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from dispatcher.api.deps import STORE, scenario_of, version_of
from dispatcher.api.envelope import ok
from dispatcher.api.payload import plan_payload
from dispatcher.api.schemas import EquipmentTransferRequest, OrderStatusRequest
from dispatcher.domain import STATUS_SENT
from dispatcher.services.equipment import transfer
from dispatcher.services.statuses import day_progress, status_of

router = APIRouter()


@router.post("/api/order/status")
def set_status(request: OrderStatusRequest) -> dict:
    """Отмечает состояние заявки: в пути, выполняется, завершено, отменена."""
    scenario = scenario_of(request.region)
    state = version_of(request.region)

    order = next((o for o in state.orders if o.id == request.order_id), None)
    if order is None:
        raise HTTPException(404, f"Заявка {request.order_id} не найдена")

    was = status_of(request.order_id, state.statuses)
    if was == request.status:
        # Повторное нажатие не должно плодить версии дня: история смены
        # нужна диспетчеру для отмены решений, а не как журнал кликов.
        return ok(plan_payload(scenario, state.plan, state.metrics))

    statuses = dict(state.statuses)
    if request.status == STATUS_SENT:
        statuses.pop(request.order_id, None)
    else:
        statuses[request.order_id] = request.status

    version = STORE.snapshot(request.region,
                             f"Заявка {request.order_id}: {request.status.lower()}")
    if version is None:
        raise HTTPException(409, "План ещё не построен")
    version.statuses = statuses
    version.manual = True
    STORE.push(request.region, version)
    return ok(plan_payload(scenario, version.plan, version.metrics))


@router.get("/api/progress/{region}")
def progress(region: str) -> dict:
    """Ход смены: сколько закрыто, отменено и в работе."""
    state = version_of(region)
    return ok(day_progress(state.orders, state.statuses))


@router.post("/api/equipment/transfer")
def transfer_equipment(request: EquipmentTransferRequest) -> dict:
    """Одна бригада отдаёт другой устройство из своей сумки.

    Заказчик: оборудование выдаётся утром, но в течение дня может
    передаваться между инженерами. Отдаётся только свободное - то, что не
    расписано под собственные заявки отдающего.
    """
    scenario = scenario_of(request.region)
    state = version_of(request.region)
    known = {engineer.id for engineer in state.engineers}
    for crew in (request.source, request.target):
        if crew not in known:
            raise HTTPException(404, f"Исполнитель {crew} не найден")

    try:
        updated = transfer(state.issued, state.plan, state.orders,
                           request.source, request.target, request.item,
                           request.count)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error

    version = STORE.snapshot(
        request.region,
        f"{request.item}: {request.source} - {request.target}, {request.count} шт")
    if version is None:
        raise HTTPException(409, "План ещё не построен")
    version.issued = updated
    version.manual = True
    STORE.push(request.region, version)
    return ok(plan_payload(scenario, version.plan, version.metrics))
