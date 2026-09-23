"""Как точечная правка ставит одну заявку, оставшуюся без бригады.

Порядок попыток: вставить как есть; если нельзя - пересобрать хвост одной
бригады; для срочной - освободить место, сначала в срок реакции. Обычная
новая заявка берёт только первый шаг и только без сдвига соседей: она не
должна перестраивать сформированный план (организаторы, 22.09).
"""
from __future__ import annotations

from dispatcher.domain import PRIORITY_URGENT, Engineer, Order, Route
from dispatcher.services.equipment import Stock
from dispatcher.services.planning.costs import ENGINEER_FIXED_COST
from dispatcher.services.replanning.displacement import (
    _place_urgent_with_displacement,
    _resequence_with,
)
from dispatcher.services.replanning.emergency import deadline_for, delay_cost, settle
from dispatcher.services.replanning.newcomer import keeps_schedule
from dispatcher.services.routing import insertion_cost


def place_orphan(order: Order, crews: list[Engineer], routes: dict[str, Route],
                 by_id: dict[str, Order], frozen: dict[str, list[str]], now: int,
                 stock: Stock, newcomer: Order | None,
                 displaced: dict[str, str]) -> None:
    """Ставит заявку к одной из `crews`, меняя `routes` на месте.

    `displaced` пополняется заявками, уступившими место срочной.
    """
    best: tuple[float, str, Route] | None = None
    for engineer in crews:
        if not engineer.can_do(order) or not stock.can_take(engineer.id, order):
            continue
        route = routes[engineer.id]
        first_free = len(frozen.get(engineer.id, []))
        for position in range(first_free, len(route.stops) + 1):
            ok, delta, new_route = insertion_cost(
                engineer, route, by_id, order, position)
            if not ok:
                continue
            if (newcomer is not None and order.id == newcomer.id
                    and new_route is not None
                    and not keeps_schedule(route, new_route)):
                continue
            score = delta + (ENGINEER_FIXED_COST / 1000.0
                             if not route.is_used else 0.0)
            if new_route is not None:
                score += delay_cost(order, new_route, now)
            if new_route is not None and (best is None or score < best[0]):
                best = (score, engineer.id, new_route)
    if best is not None:
        settle(order, best, routes, crews, by_id, frozen, now, stock, displaced)
        return

    if newcomer is not None and order.id == newcomer.id:
        return

    # Вставка «как есть» не удалась - пробуем пересобрать хвост маршрута.
    for engineer in crews:
        if not engineer.can_do(order) or not stock.can_take(engineer.id, order):
            continue
        route = routes[engineer.id]
        first_free = len(frozen.get(engineer.id, []))
        attempt = _resequence_with(engineer, route, by_id, order, first_free)
        if attempt is None:
            continue
        delta, new_route = attempt
        score = delta + (ENGINEER_FIXED_COST / 1000.0
                         if not route.is_used else 0.0)
        score += delay_cost(order, new_route, now)
        if best is None or score < best[0]:
            best = (score, engineer.id, new_route)
    if best is not None:
        settle(order, best, routes, crews, by_id, frozen, now, stock, displaced)
        return

    # Срочная заявка не встала и после пересборки - освобождаем ей место:
    # сначала так, чтобы бригада успела в срок, и только потом где угодно.
    if order.priority == PRIORITY_URGENT:
        outcome = (_place_urgent_with_displacement(
                       order, routes, crews, by_id, frozen, now, stock,
                       deadline=deadline_for(order, now))
                   or _place_urgent_with_displacement(
                       order, routes, crews, by_id, frozen, now, stock))
        if outcome is not None:
            _, homeless = outcome
            for victim in homeless:
                displaced[victim.id] = order.id
