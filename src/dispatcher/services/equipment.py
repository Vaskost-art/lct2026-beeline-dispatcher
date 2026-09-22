"""Ведомость на выдачу оборудования и остаток в сумке бригады.

Заказчик описал это так: с утра система видит спланированные заявки и по ним
понимает, что везти; оборудование бригада получает сразу на весь день. Отсюда
два вопроса: что выдать утром и что бригада может взять днём - назначить ей
можно только заявку, под которую оборудование у неё с собой есть.
"""
from __future__ import annotations

from typing import TypedDict

from dispatcher.domain import Order, Plan
from dispatcher.domain.equipment import EQUIPMENT, FORMS, SPARE_PER_ITEM
from dispatcher.domain.text import plural


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
            one, few, many = FORMS[name]
            parts.append(f"{count} {plural(count, one, few, many)}")
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


def issued_items(plan: Plan, orders: list[Order]) -> dict[str, dict[str, int]]:
    """Что бригады получили в офисе утром: план плюс запас.

    Считается один раз, по первому плану дня: оборудование выдаётся сразу на
    весь день, и днём сумка бригады уже не меняется.
    """
    issued: dict[str, dict[str, int]] = {}
    for row in pickup_list(plan, orders):
        items = dict(row["items"])
        for name in EQUIPMENT:
            items[name] = items.get(name, 0) + SPARE_PER_ITEM
        issued[row["engineer_id"]] = items
    return issued


def planned_items(plan: Plan, orders: list[Order],
                  engineer_id: str) -> dict[str, int]:
    """Что уже расписано бригаде по текущему плану."""
    for row in pickup_list(plan, orders):
        if row["engineer_id"] == engineer_id:
            return dict(row["items"])
    return {}


def missing_for(order: Order, engineer_id: str, issued: dict[str, dict[str, int]],
                plan: Plan, orders: list[Order]) -> list[str]:
    """Чего не хватит бригаде, если отдать ей эту заявку.

    Пустой список значит, что заявку взять можно. Пока ведомость не выдана
    (день ещё не построен), ограничения нет: бригада забирает набор в офисе
    уже под готовый план.
    """
    if not issued or not order.equipment:
        return []
    carried = issued.get(engineer_id, {})
    busy = planned_items(plan, orders, engineer_id)
    short = []
    for name in order.equipment:
        busy[name] = busy.get(name, 0) + 1
        if busy[name] > carried.get(name, 0):
            short.append(name)
    return short


class Stock:
    """Что осталось в сумках бригад по ходу дня.

    Перепланирование раздаёт заявки десятками, и считать ведомость заново на
    каждую попытку дорого. Остаток ведётся здесь: заявка занимает место при
    назначении и освобождает при снятии.
    """

    def __init__(self, issued: dict[str, dict[str, int]]) -> None:
        self._issued = issued
        self._load: dict[str, dict[str, int]] = {}

    @property
    def enforced(self) -> bool:
        """Ограничение работает только после утренней выдачи."""
        return bool(self._issued)

    def fill(self, sequences: dict[str, list[Order]]) -> None:
        """Занимает места под уже назначенные заявки."""
        self._load = {}
        for engineer_id, sequence in sequences.items():
            for order in sequence:
                self.take(engineer_id, order)

    def can_take(self, engineer_id: str, order: Order) -> bool:
        if not self._issued or not order.equipment:
            return True
        carried = self._issued.get(engineer_id, {})
        busy = self._load.get(engineer_id, {})
        need: dict[str, int] = {}
        for name in order.equipment:
            need[name] = need.get(name, 0) + 1
        return all(busy.get(name, 0) + count <= carried.get(name, 0)
                   for name, count in need.items())

    def take(self, engineer_id: str, order: Order) -> None:
        busy = self._load.setdefault(engineer_id, {})
        for name in order.equipment:
            busy[name] = busy.get(name, 0) + 1

    def release(self, engineer_id: str, order: Order) -> None:
        busy = self._load.setdefault(engineer_id, {})
        for name in order.equipment:
            busy[name] = max(0, busy.get(name, 0) - 1)
