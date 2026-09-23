"""Остаток в сумке бригады и передача оборудования между бригадами.

Назначить заявку можно только тому, у кого нужное устройство с собой, а
пополнить сумку в поле нечем - кроме как взять у соседа: заказчик разрешил
передавать оборудование между инженерами в течение дня.
"""
from __future__ import annotations

from dispatcher.domain import Order, Plan
from dispatcher.domain.equipment import EQUIPMENT, FORMS
from dispatcher.domain.text import plural
from dispatcher.services.equipment.sheet import pickup_list


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


def transfer(issued: dict[str, dict[str, int]], plan: Plan, orders: list[Order],
             source: str, target: str, item: str,
             count: int) -> dict[str, dict[str, int]]:
    """Передаёт оборудование от бригады к бригаде в течение дня.

    Заказчик: оборудование выдаётся утром, но в течение дня может
    передаваться между инженерами. Отдать можно только свободное - то, что
    не расписано под собственные заявки отдающего: иначе он сам приедет к
    клиенту без устройства.

    Возвращает новую ведомость. Ошибку описывает `ValueError`.
    """
    if count <= 0:
        raise ValueError("Передать можно хотя бы одно устройство")
    if source == target:
        raise ValueError("Бригада-отправитель и получатель совпадают")
    if item not in EQUIPMENT:
        raise ValueError(f"Неизвестное оборудование: {item}")

    carried = issued.get(source, {}).get(item, 0)
    busy = planned_items(plan, orders, source).get(item, 0)
    free = carried - busy
    if free < count:
        one, few, many = FORMS[item]
        raise ValueError(
            f"У бригады «{source}» свободно {free} "
            f"{plural(free, one, few, many)}: под её заявки нужно {busy} "
            f"из {carried}")

    updated = {crew: dict(items) for crew, items in issued.items()}
    updated.setdefault(source, {})[item] = carried - count
    updated.setdefault(target, {})
    updated[target][item] = updated[target].get(item, 0) + count
    return updated
