"""Замороженная часть дня: то, что бригада уже выполнила к моменту события.

Выполненное до события не пересматривается: в противном случае
перепланирование стирает работу, которая уже сделана.
"""
from __future__ import annotations

from copy import deepcopy

from dispatcher.domain import Engineer, Order, Plan


def _frozen_prefixes(plan: Plan, now: int) -> dict[str, list[str]]:
    """Заявки, к которым уже приступили: менять их нельзя."""
    frozen: dict[str, list[str]] = {}
    for route in plan.routes:
        started = [s.order_id for s in route.stops if s.start <= now]
        if started:
            frozen[route.engineer_id] = started
    return frozen


def merge_frozen(by_clock: dict[str, list[str]],
                  by_fact: dict[str, list[str]]) -> dict[str, list[str]]:
    """Замороженное по расписанию плюс замороженное по факту.

    Порядок внутри маршрута задаёт расписание, поэтому списки склеиваются с
    сохранением очерёдности, а повторы убираются.
    """
    merged: dict[str, list[str]] = {}
    for engineer_id in set(by_clock) | set(by_fact):
        seen: dict[str, None] = {}
        for order_id in [*by_clock.get(engineer_id, []),
                         *by_fact.get(engineer_id, [])]:
            seen.setdefault(order_id, None)
        merged[engineer_id] = list(seen)
    return merged


def shifts_after_event(current: Plan, orders: list[Order],
                       engineers: list[Engineer], frozen: dict[str, list[str]],
                       now: int) -> list[Engineer]:
    """Смены на остаток дня: что заморожено, то обязано в них помещаться.

    Бригада, у которой ничего не начато, начинает остаток дня «сейчас». У
    остальных конец смены отодвигается ровно настолько, чтобы начатая
    работа поместилась: иначе замороженный префикс не проходит пересчёт, и
    весь день бригады пропадает из плана.
    """
    frozen_end: dict[str, int] = {}
    plannable_by_id = {o.id: o for o in orders}
    for route in current.routes:
        ids = frozen.get(route.engineer_id) or []
        for stop in route.stops:
            if stop.order_id not in ids:
                continue
            planned = plannable_by_id.get(stop.order_id)
            # длительность могла вырасти: задержка записывается в неё
            end = stop.start + (planned.duration_min if planned else
                                stop.end - stop.start)
            frozen_end[route.engineer_id] = max(
                frozen_end.get(route.engineer_id, 0), end)

    # Исполнители, у которых ничего не заморожено, начинают остаток дня «сейчас».
    adjusted: list[Engineer] = []
    for engineer in engineers:
        e = deepcopy(engineer)
        if not frozen.get(e.id):
            e.shift_start = max(e.shift_start, min(now, e.shift_end))
        need = frozen_end.get(e.id)
        if need is not None and e.work_end < need:
            # Ровно столько, чтобы начатое поместилось: свободного места
            # после него не появляется.
            e.shift_end = need + e.break_min
        adjusted.append(e)
    return adjusted
