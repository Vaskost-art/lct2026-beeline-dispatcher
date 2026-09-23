"""Сумка бригады в решателе: не больше устройств, чем выдано утром.

Оборудование выдаётся в офисе на весь день, и днём заявку можно отдать только
бригаде, у которой нужное устройство с собой (организаторы, 19.09). Точечная
правка это соблюдала, а пересборка дня нет: бригада получала шесть роутеров
при трёх выданных.
"""
from __future__ import annotations

from ortools.constraint_solver import pywrapcp

from dispatcher.domain import Engineer, Order
from dispatcher.domain.equipment import EQUIPMENT


def limit_bags(routing: pywrapcp.RoutingModel,
               manager: pywrapcp.RoutingIndexManager,
               orders: list[Order], engineers: list[Engineer],
               issued: dict[str, dict[str, int]]) -> None:
    """Для каждого вида устройства - ёмкость бригады по утренней выдаче.

    Пустая выдача значит «утром ещё не выдавали»: ограничения нет, набор
    соберётся по готовому плану.
    """
    if not issued:
        return
    n_orders = len(orders)
    for item in EQUIPMENT:
        needs = [order.equipment.count(item) for order in orders]
        if not any(needs):
            continue

        def demand(from_index: int, table: list[int] = needs) -> int:
            node: int = manager.IndexToNode(from_index)
            return table[node] if node < n_orders else 0

        callback = routing.RegisterUnaryTransitCallback(demand)
        capacity = [issued.get(engineer.id, {}).get(item, 0) for engineer in engineers]
        routing.AddDimensionWithVehicleCapacity(callback, 0, capacity, True, f"bag:{item}")
