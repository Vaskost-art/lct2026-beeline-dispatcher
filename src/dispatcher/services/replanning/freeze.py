"""Замороженная часть дня: то, что бригада уже выполнила к моменту события.

Выполненное до события не пересматривается: в противном случае
перепланирование стирает работу, которая уже сделана.
"""
from __future__ import annotations

from dispatcher.domain import Plan


def _frozen_prefixes(plan: Plan, now: int) -> dict[str, list[str]]:
    """Заявки, к которым уже приступили: менять их нельзя."""
    frozen: dict[str, list[str]] = {}
    for route in plan.routes:
        started = [s.order_id for s in route.stops if s.start <= now]
        if started:
            frozen[route.engineer_id] = started
    return frozen
