"""Новая заявка в течение дня: авария и всё остальное.

Организаторы (22.09): новая обычная заявка, если помещается в свободный
интервал инженера между уже запланированными работами, может быть
добавлена, но не должна перестраивать сформированный план. Авария может
перепланировать остаток дня.

«Свободный интервал» здесь понимается строго: соседние визиты не сдвигаются
ни на минуту. Клиентам уже назвали время, и ради обычной заявки его не
переносят - это право аварии.
"""
from __future__ import annotations

from dispatcher.domain import PRIORITY_URGENT, Engineer, Order, Plan, Route, Unassigned
from dispatcher.services.planning.reasons import diagnose
from dispatcher.services.replanning.displacement import REASON_DISPLACED
from dispatcher.services.replanning.events import KIND_URGENT, ReplanEvent

REASON_NO_FREE_SLOT = "no_free_slot"


def ordinary_newcomer(event: ReplanEvent) -> Order | None:
    """Новая заявка события, если это не авария. Иначе None."""
    order = event.new_order
    if event.kind != KIND_URGENT or order is None:
        return None
    return None if order.priority == PRIORITY_URGENT else order


def keeps_schedule(before: Route, after: Route) -> bool:
    """Все прежние визиты маршрута начинаются в то же время, что и раньше."""
    starts = {stop.order_id: stop.start for stop in after.stops}
    return all(starts.get(stop.order_id) == stop.start for stop in before.stops)


def no_free_slot(order: Order) -> Unassigned:
    """Причина для диспетчера, почему обычная заявка осталась без бригады."""
    return Unassigned(
        order_id=order.id, reason=REASON_NO_FREE_SLOT,
        reason_text=(f"Ни у одной подходящей бригады нет свободного окна под "
                     f"{order.duration_min} мин в интервале {order.window_text}. "
                     f"Двигать уже назначенные визиты ради обычной заявки "
                     f"нельзя - это право аварии. Заявку можно передать "
                     f"вручную или перенести на другой день."),
    )


def repair_reason(order: Order, engineers: list[Engineer], displaced: dict[str, str],
            newcomer: Order | None) -> Unassigned:
    """Почему заявка осталась без бригады после починки дня."""
    if newcomer is not None and order.id == newcomer.id:
        return no_free_slot(order)
    if order.id in displaced:
        return Unassigned(
            order_id=order.id, reason=REASON_DISPLACED,
            reason_text=f"Уступила место аварии {displaced[order.id]}: без этого "
                        f"бригада не успевала к аварии в срок (ориентир "
                        f"организаторов - 1-2 часа). Другой бригады с местом "
                        f"не нашлось. Окно {order.window_text}, требуется навык "
                        f"«{order.required_skill}».")
    return diagnose(order, engineers)


def newcomer_outcome(plan: Plan, event: ReplanEvent) -> dict[str, object] | None:
    """Что стало с заявкой, поступившей днём: у кого она или почему ни у кого.

    Диспетчер смотрит предпросмотр ради этого ответа. Список «что изменится»
    его не даёт: не вставшей новой заявки там нет, её не было в плане.
    """
    order = event.new_order
    if event.kind != KIND_URGENT or order is None:
        return None
    for route in plan.routes:
        if any(stop.order_id == order.id for stop in route.stops):
            return {"order_id": order.id, "priority": order.priority,
                    "engineer_id": route.engineer_id, "reason": None}
    reason = next((item.reason_text for item in plan.unassigned
                   if item.order_id == order.id), "Причина не определена.")
    return {"order_id": order.id, "priority": order.priority,
            "engineer_id": None, "reason": reason}
