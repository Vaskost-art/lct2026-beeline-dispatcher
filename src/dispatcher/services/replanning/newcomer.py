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
from dispatcher.services.planning.costs import URGENT_DELAY_COST_PER_MIN
from dispatcher.services.planning.reasons import diagnose
from dispatcher.services.replanning.displacement import REASON_DISPLACED
from dispatcher.services.replanning.events import KIND_URGENT, ReplanEvent

REASON_NO_FREE_SLOT = "no_free_slot"

#: Цена километра в целевой функции решателя: дуга весит метры пробега.
KM_COST = 1000


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
            reason_text=f"Вытеснена срочной заявкой {displaced[order.id]}: "
                        f"освободить место было больше негде. Окно "
                        f"{order.window_text}, требуется навык "
                        f"«{order.required_skill}».")
    return diagnose(order, engineers)


#: Ориентир организаторов (22.09): для сетевой аварии допустимо закладывать
#: время реакции 1-2 часа. Верхнюю границу и проверяем.
REACTION_TARGET_MIN = 120


def reaction(plan: Plan, event: ReplanEvent) -> dict[str, object] | None:
    """Через сколько бригада приедет на аварию, поступившую днём.

    Считается от поступления до прибытия, а не до начала работ: ожидание
    открытия окна - не задержка реакции, бригада уже на месте. Для
    обычной заявки и для аварии, которой не нашлось бригады, ответа нет.
    """
    order = event.new_order
    if event.kind != KIND_URGENT or order is None or order.priority != PRIORITY_URGENT:
        return None
    for route in plan.routes:
        for stop in route.stops:
            if stop.order_id == order.id:
                minutes = stop.arrival - event.at
                return {"engineer_id": route.engineer_id, "minutes": minutes,
                        "target_min": REACTION_TARGET_MIN,
                        "within": minutes <= REACTION_TARGET_MIN}
    return None


def describe_reaction(info: dict[str, object]) -> str:
    """Строка для рассказа о событии."""
    minutes = int(str(info["minutes"]))
    spent = f"{minutes // 60} ч {minutes % 60} мин" if minutes >= 60 else f"{minutes} мин"
    verdict = ("в пределах ориентира 1-2 часа" if info["within"]
               else "дольше ориентира 1-2 часа: стоит проверить, нельзя ли "
                    "снять с ближней бригады обычную заявку вручную")
    return (f"«{info['engineer_id']}» прибудет на аварию через {spent} после "
            f"её поступления - {verdict}.")


def stuck_emergencies(plan: Plan, orders: list[Order]) -> list[str]:
    """Срочные заявки, не вставшие точечной правкой, и что с этим делать.

    Это решение диспетчера, а не тупик: называем причину из диагностики -
    она может быть любой, от нехватки навыка до занятого окна, - и говорим,
    чем придётся заплатить за другой режим.
    """
    placed = {stop.order_id for route in plan.routes for stop in route.stops}
    reasons = {item.order_id: item.reason_text for item in plan.unassigned}
    return [f"Срочная заявка {order.id} не размещена точечной правкой. "
            f"{reasons.get(order.id, 'Причина не определена.')} "
            f"Попробуйте режим «Пересобрать остаток дня»: он может найти для "
            f"неё место ценой перестановок в маршрутах и, возможно, снятия "
            f"другой заявки. Решение за диспетчером."
            for order in orders
            if order.priority == PRIORITY_URGENT and order.id not in placed]


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


def delay_cost(order: Order, route: Route, now: int) -> float:
    """Цена ожидания аварии в километрах - как в решателе.

    Точечная правка выбирала место по приросту пробега и отправляла аварию
    в конец чужого дня: реакция выходила 5-7 часов при ориентире
    организаторов 1-2 часа. Минута ожидания стоит столько же, сколько в
    целевой функции решателя, поэтому оба режима разменивают время и
    километры одинаково. Для обычной заявки цена нулевая.
    """
    if order.priority != PRIORITY_URGENT:
        return 0.0
    stop = next((item for item in route.stops if item.order_id == order.id), None)
    if stop is None:
        return 0.0
    waited = max(0, stop.start - max(order.window_start, now))
    return waited * URGENT_DELAY_COST_PER_MIN / KM_COST
