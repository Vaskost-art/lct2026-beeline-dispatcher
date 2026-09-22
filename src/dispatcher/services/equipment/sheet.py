"""Ведомость на выдачу: что бригада забирает в офисе утром.

Заказчик описал это так: с утра система видит спланированные заявки и по ним
понимает, что везти; оборудование бригада получает сразу на весь день.
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


def name_listing(names: list[str]) -> str:
    """«роутера» или «роутера и приставки»: перечень для текста отказа.

    Берётся форма родительного падежа из того же справочника, что и счёт в
    ведомости: «нет роутер» диспетчер читает как машинный вывод.
    """
    unique = list(dict.fromkeys(names))
    words = [FORMS[name][1] if name in FORMS else name.lower() for name in unique]
    if len(words) == 1:
        return words[0]
    return ", ".join(words[:-1]) + " и " + words[-1]


def issued_rows(issued: dict[str, dict[str, int]]) -> list[PickupRow]:
    """Ведомость по выданному: то же, что видит кладовщик и что в сумке.

    Показывать расчёт по текущему плану нельзя: бригада уехала с запасом,
    и экран расходился бы с тем, по чему система принимает решения.
    """
    rows: list[PickupRow] = []
    for engineer_id, items in issued.items():
        counted = {name: count for name, count in items.items() if count}
        total = sum(counted.values())
        if not total:
            continue
        rows.append({"engineer_id": engineer_id, "items": counted,
                     "total": total, "text": _describe(counted)})
    return rows
