"""Матрица времени перехода для решателя: работа в точке плюс дорога."""
from __future__ import annotations

from dispatcher.domain import Order
from dispatcher.domain.distance import travel_minutes


def transit_matrix(km: list[list[float]], orders: list[Order], n_orders: int,
                    end_node: int, vehicle: str) -> list[list[int]]:
    """Время перехода i -> j: работа в точке i плюс дорога этим транспортом."""
    size = len(km)
    matrix = [[0] * size for _ in range(size)]
    for i in range(size):
        service = orders[i].duration_min if i < n_orders else 0
        for j in range(size):
            if j == end_node or i in (end_node, j):
                matrix[i][j] = service
            else:
                matrix[i][j] = service + travel_minutes(km[i][j], vehicle)
    return matrix
