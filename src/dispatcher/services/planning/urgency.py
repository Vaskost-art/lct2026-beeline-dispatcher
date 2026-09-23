"""Срочные заявки в решателе: как можно раньше, а поступившие днём - в срок.

Мягкие границы, а не жёсткие: жёсткая выкинула бы заявку из плана, если
бригада не успевает, а нужно «как можно раньше», а не «либо рано, либо никак».
"""
from __future__ import annotations

from ortools.constraint_solver import pywrapcp

from dispatcher.domain import PRIORITY_URGENT, Engineer, Order
from dispatcher.services.planning.costs import (
    LATE_EMERGENCY_COST_PER_MIN,
    URGENT_DELAY_COST_PER_MIN,
)


def rush_emergencies(manager: pywrapcp.RoutingIndexManager,
                     time_dim: pywrapcp.RoutingDimension,
                     orders: list[Order], engineers: list[Engineer],
                     deadlines: dict[str, int]) -> None:
    """Тянет срочные к началу окна, а аварию, поступившую днём, - к сроку."""
    earliest = min((e.shift_start for e in engineers), default=0)
    for node, order in enumerate(orders):
        if order.priority != PRIORITY_URGENT:
            continue
        index = manager.NodeToIndex(node)
        if order.id in deadlines:
            # Авария, поступившая днём: до срока реакции ожидание бесплатно,
            # после - дороже снятого ремонта за каждые полчаса.
            time_dim.SetCumulVarSoftUpperBound(index, deadlines[order.id],
                                               LATE_EMERGENCY_COST_PER_MIN)
            continue
        bound = max(order.window_start, earliest)
        time_dim.SetCumulVarSoftUpperBound(index, bound, URGENT_DELAY_COST_PER_MIN)
