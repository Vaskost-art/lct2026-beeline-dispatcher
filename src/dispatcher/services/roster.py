"""Кто вышел на смену: бригады, получившие заявки в плане дня.

Организаторы (22.09, 24.09): бригада, которой утренний план не дал заявок,
в этот день не выходит. Новая заявка или авария днём её из дома не
вызывает: это форс-мажор, и решает его диспетчер вручную.
"""
from __future__ import annotations

from collections.abc import Iterable

from dispatcher.domain import Engineer, Order, Plan, Route


def roster_of(plan: Plan, carried: Iterable[str] = ()) -> list[str]:
    """Прежний состав смены плюс все, у кого в плане есть заявки."""
    names = dict.fromkeys(carried)
    for route in plan.routes:
        if route.stops:
            names.setdefault(route.engineer_id)
    return list(names)


def working_crews(engineers: list[Engineer], on_shift: Iterable[str] | None,
                  frozen: dict[str, list[str]]) -> list[Engineer]:
    """Бригады, которым можно раздавать работу днём.

    None - состав неизвестен (день поднят из записи без него): на смене все.
    """
    if on_shift is None:
        return engineers
    allowed = set(on_shift) | set(frozen)
    return [e for e in engineers if e.id in allowed]


def add_home_crews(plan: Plan, engineers: list[Engineer], orders: list[Order],
                   working: list[Engineer]) -> None:
    """Возвращает в план бригады, оставшиеся дома, и называет их в отказах.

    Маршрут у них пустой, но в плане они есть: иначе экран терял бригаду
    из списка. В причине отказа диспетчер видит, кого можно вызвать.
    """
    at_work = {e.id for e in working}
    home = [e for e in engineers if e.id not in at_work]
    if not home:
        return
    listed = {route.engineer_id for route in plan.routes}
    plan.routes.extend(Route(engineer_id=e.id) for e in home if e.id not in listed)
    by_id = {order.id: order for order in orders}
    for item in plan.unassigned:
        order = by_id.get(item.order_id)
        able = [e.name for e in home if order is not None and e.can_do(order)]
        if able:
            item.reason_text += (f" Сегодня не на смене: {', '.join(able)}. "
                                 f"Вызвать с выходного можно только вручную.")
