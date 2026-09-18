"""Ведомость на выдачу оборудования.

Заказчик описал это так: с утра система видит спланированные заявки и по ним
понимает, что везти. Значит ведомость считается по готовому плану, а не
ограничивает его.
"""
from __future__ import annotations

from typing import TypedDict

from dispatcher.domain import Order, Plan
from dispatcher.domain.equipment import EQUIPMENT


class PickupRow(TypedDict):
    """Что одна бригада забирает в офисе перед выездом."""

    engineer_id: str
    items: dict[str, int]
    total: int
    text: str


def _describe(items: dict[str, int]) -> str:
    """Строка для человека: «2 роутера, 1 приставка»."""
    parts = []
    for name in EQUIPMENT:
        count = items.get(name, 0)
        if count:
            parts.append(f"{count} {name.lower()}")
    return ", ".join(parts)


def pickup_list(plan: Plan, orders: list[Order]) -> list[PickupRow]:
    """Ведомость по каждой бригаде, у которой есть что забирать."""
    by_id = {order.id: order for order in orders}
    rows: list[PickupRow] = []
    for route in plan.routes:
        items: dict[str, int] = {}
        for stop in route.stops:
            order = by_id.get(stop.order_id)
            if order is None:
                continue
            for name in order.equipment:
                items[name] = items.get(name, 0) + 1
        total = sum(items.values())
        if not total:
            continue
        rows.append({
            "engineer_id": route.engineer_id,
            "items": items,
            "total": total,
            "text": _describe(items),
        })
    return rows
