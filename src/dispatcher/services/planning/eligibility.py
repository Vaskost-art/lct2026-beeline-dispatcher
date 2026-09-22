"""Кто вправе взять заявку и сколько стоит её не взять.

Ограничения ТЗ «Навык» и «Ресурс» выражаются списком допустимых бригад:
решатель не может назначить заявку тому, у кого нет навыка или транспорта.
Цена пропуска задаёт порядок постановщика: авария, подключение, остальное.
"""
from __future__ import annotations

from ortools.constraint_solver import pywrapcp

from dispatcher.domain import (
    PRIORITY_HIGH,
    PRIORITY_NORMAL,
    PRIORITY_URGENT,
    Engineer,
    Order,
)
from dispatcher.services.planning.costs import (
    DROP_PENALTY_HIGH,
    DROP_PENALTY_NORMAL,
    DROP_PENALTY_URGENT,
)

#: Цена пропуска по приоритету: авария, подключение, остальное.
PENALTY_BY_PRIORITY = {
    PRIORITY_URGENT: DROP_PENALTY_URGENT,
    PRIORITY_HIGH: DROP_PENALTY_HIGH,
    PRIORITY_NORMAL: DROP_PENALTY_NORMAL,
}


def restrict_crews(routing: pywrapcp.RoutingModel,
                   manager: pywrapcp.RoutingIndexManager,
                   orders: list[Order], engineers: list[Engineer],
                   locked: dict[str, str]) -> None:
    """Каждой заявке - список бригад, которые вправе её взять."""
    for node, order in enumerate(orders):
        index = manager.NodeToIndex(node)
        allowed = [v for v, e in enumerate(engineers) if e.can_do(order)]

        pinned = locked.get(order.id)
        if pinned is not None:
            allowed = [v for v, e in enumerate(engineers)
                       if e.id == pinned and v in allowed]

        if not allowed:
            # Заявку не может взять никто. Домен из одного значения -1
            # означает «обязана остаться неназначенной»: без этого солвер
            # вправе отдать её любому исполнителю, и план нарушит
            # ограничение по навыку или по транспорту.
            routing.VehicleVar(index).SetValues([-1])
            routing.AddDisjunction([index], 0)
            continue

        # -1 в домене означает «заявка не назначена»: без него солвер не смог бы
        # снять заявку, для которой не хватает ресурсов.
        routing.VehicleVar(index).SetValues([-1] + allowed)
        penalty = PENALTY_BY_PRIORITY.get(order.priority, DROP_PENALTY_NORMAL)
        routing.AddDisjunction([index], penalty)
