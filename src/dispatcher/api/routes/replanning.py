"""События в течение дня."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from dispatcher.api.deps import STORE, day, scenario_of, version_of
from dispatcher.api.payload import plan_payload
from dispatcher.api.schemas import ReplanRequest
from dispatcher.api.state import DayVersion, PreviewCache
from dispatcher.domain import PRIORITY_URGENT, hhmm, parse_hhmm
from dispatcher.services.dataset import DatasetError, order_from_json
from dispatcher.services.metrics import plan_metrics
from dispatcher.services.replanning.apply import replan
from dispatcher.services.replanning.events import (
    KIND_CANCEL,
    KIND_DELAYED,
    KIND_TITLES,
    KIND_UNAVAILABLE,
    KIND_URGENT,
    ReplanEvent,
    make_urgent_order,
)

router = APIRouter()


# --- перепланирование --------------------------------------------------------

@router.post("/api/replan")
def do_replan(request: ReplanRequest) -> dict:
    scenario = scenario_of(request.region)
    state = version_of(request.region)
    orders, engineers = state.orders, state.engineers

    try:
        at = parse_hhmm(request.at)
    except ValueError as error:
        raise HTTPException(400, "Время события должно быть в формате ЧЧ:ММ") from error

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
                "priority": PRIORITY_URGENT,
                "required_skill": payload.required_skill,
                "required_vehicle": payload.required_vehicle,
            })
        except DatasetError as exc:
            raise HTTPException(400, str(exc)) from exc

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
    state_day = day(request.region)
    version_number = len(state_day.versions)
    preview = state_day.preview
    if (request.apply and preview is not None
            and preview.signature == signature
            and preview.version_number == version_number):
        result = preview.result
    else:
        result = replan(orders, engineers, state.plan, event,
                        mode=request.mode,
                        time_limit_sec=request.time_limit_sec)
        if not request.apply:
            state_day.preview = PreviewCache(signature, version_number, result)

    # Списки после события берём у самого переплана, а не пересобираем здесь:
    # событие может менять не только состав заявок, но и их поля (задержка
    # бригады удлиняет начатый визит), и вторая независимая сборка
    # разъезжается с планом — план перестаёт проходить проверку.
    new_orders = result.orders
    new_engineers = result.engineers

    metrics = plan_metrics(result.plan, new_orders, new_engineers)

    if request.apply:
        # Смены сдвинулись: остаток дня начинается с момента события, у
        # выбывшей бригады смена закрыта.
        STORE.push(request.region, DayVersion(
            label=f"{KIND_TITLES.get(request.kind, request.kind)} в {hhmm(at)}",
            plan=result.plan, metrics=metrics,
            orders=new_orders, engineers=new_engineers,
            locked=dict(state.locked)))
        state_day.preview = None
        return plan_payload(scenario, result.plan, metrics, extra={
            "diff": result.diff,
            "narrative": result.narrative,
            "applied": True,
            "frozen": result.frozen,
        })

    # Предпросмотр: показываем, что получится, не меняя рабочий день. Заявки
    # после события подставляем только в ответ.
    preview_version = DayVersion(label="предпросмотр", plan=result.plan,
                                 metrics=metrics, orders=new_orders,
                                 engineers=new_engineers, locked=dict(state.locked))
    state_day.versions.append(preview_version)
    try:
        return plan_payload(scenario, result.plan, metrics, extra={
            "diff": result.diff,
            "narrative": result.narrative,
            "applied": False,
            "frozen": result.frozen,
        })
    finally:
        state_day.versions.pop()
