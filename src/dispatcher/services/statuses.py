"""Состояние заявок в течение смены.

Организаторы: факт выполнения или отмены фиксирует диспетчер со слов
бригады, закрытые заявки в дальнейшее планирование не включаются.

Отсюда два правила, которыми пользуются перепланирование и ручные правки:
закрытую заявку не планируют заново, а начатую не снимают с бригады.
"""
from __future__ import annotations

from dispatcher.domain import (
    CLOSED_STATUSES,
    STARTED_STATUSES,
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_SENT,
    Order,
    Plan,
)


def status_of(order_id: str, statuses: dict[str, str]) -> str:
    """Статус заявки. Не отмеченная заявка считается отправленной."""
    return statuses.get(order_id) or STATUS_SENT


def is_closed(order_id: str, statuses: dict[str, str]) -> bool:
    """Работа закончена или отменена: планировать больше нечего."""
    return status_of(order_id, statuses) in CLOSED_STATUSES


def is_started(order_id: str, statuses: dict[str, str]) -> bool:
    """Бригада уже в пути или на адресе: снимать такую заявку нельзя."""
    return status_of(order_id, statuses) in STARTED_STATUSES


def plannable(orders: list[Order], statuses: dict[str, str]) -> list[Order]:
    """Заявки, которые ещё нужно куда-то ставить.

    Отменённые уходят из дня совсем; завершённые остаются в плане на своих
    местах, но заново не распределяются - это делает `frozen_by_status`.
    """
    return [order for order in orders
            if status_of(order.id, statuses) != STATUS_CANCELLED]


def frozen_by_status(plan: Plan, statuses: dict[str, str]) -> dict[str, list[str]]:
    """Что нельзя трогать: начатое и завершённое, по каждой бригаде.

    Замораживается префикс маршрута - от начала и до последней тронутой
    заявки включительно. Иначе выполненная третья заявка осталась бы на
    месте, а первая и вторая уехали бы после неё.
    """
    frozen: dict[str, list[str]] = {}
    for route in plan.routes:
        kept: list[str] = []
        last_touched = -1
        for position, stop in enumerate(route.stops):
            status = status_of(stop.order_id, statuses)
            if status in STARTED_STATUSES or status == STATUS_DONE:
                last_touched = position
        if last_touched < 0:
            continue
        for stop in route.stops[:last_touched + 1]:
            if status_of(stop.order_id, statuses) != STATUS_CANCELLED:
                kept.append(stop.order_id)
        if kept:
            frozen[route.engineer_id] = kept
    return frozen


def day_progress(orders: list[Order], statuses: dict[str, str]) -> dict[str, int]:
    """Сколько заявок закрыто, отменено и в работе: ход смены."""
    counts = {"done": 0, "cancelled": 0, "in_progress": 0, "sent": 0}
    for order in orders:
        status = status_of(order.id, statuses)
        if status == STATUS_DONE:
            counts["done"] += 1
        elif status == STATUS_CANCELLED:
            counts["cancelled"] += 1
        elif status in STARTED_STATUSES:
            counts["in_progress"] += 1
        else:
            counts["sent"] += 1
    return counts
