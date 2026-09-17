"""Извлечение маршрутов из решения OR-Tools.

Решатель отдаёт последовательность точек, а времена и пробег считает
общий построитель маршрута: это единственный способ гарантировать, что
числа на экране и числа в модели совпадают.
"""
from __future__ import annotations

from dispatcher.domain import Engineer, Order, Route
from dispatcher.services.routing import evaluate_sequence


def routes_from_solution(routing, manager, solution, orders: list[Order],
                         engineers: list[Engineer]) -> list[Route]:
    """Собирает маршруты по решению, пересчитывая времена общим кодом."""
    n_orders = len(orders)
    routes: list[Route] = []
    for vehicle_id, engineer in enumerate(engineers):
        sequence: list[Order] = []
        index = routing.Start(vehicle_id)
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if node < n_orders:
                sequence.append(orders[node])
            index = solution.Value(routing.NextVar(index))
        route, _ = evaluate_sequence(engineer, sequence)
        while route is None and sequence:
            # Страховка: если пересчёт всё же не сошёлся с моделью, отдаём
            # столько заявок, сколько помещается, а не теряем весь маршрут.
            sequence = sequence[:-1]
            route, _ = evaluate_sequence(engineer, sequence)
        routes.append(route if route is not None else Route(engineer_id=engineer.id))
    return routes
