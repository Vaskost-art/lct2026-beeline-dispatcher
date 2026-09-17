"""Базовый вариант из ТЗ и жадная эвристика.

Базовый вариант задан дословно: заявки берутся по порядку поступления и
назначаются первому подходящему исполнителю, глобальной оптимизации нет.
Он нужен как честная точка отсчёта для сравнения метрик.
"""
from __future__ import annotations

import time

from dispatcher.domain import PRIORITY_URGENT, Engineer, Order, Plan, Route
from dispatcher.services.planning.costs import ENGINEER_FIXED_COST
from dispatcher.services.planning.reasons import diagnose
from dispatcher.services.routing import evaluate_sequence, insertion_cost


def _finalize(plan: Plan, orders: list[Order], engineers: list[Engineer]) -> Plan:
    """Заполняет причины по всем заявкам, не попавшим в маршруты."""
    assigned = {s.order_id for r in plan.routes for s in r.stops}
    by_id = {o.id: o for o in orders}
    plan.unassigned = [diagnose(by_id[oid], engineers)
                       for oid in (o.id for o in orders) if oid not in assigned]
    return plan



def solve_baseline(orders: list[Order], engineers: list[Engineer],
                   locked: dict[str, str] | None = None) -> Plan:
    """Последовательное распределение «как есть» — точка отсчёта из ТЗ."""
    started = time.perf_counter()
    locked = locked or {}
    routes = {e.id: Route(engineer_id=e.id) for e in engineers}
    sequences: dict[str, list[Order]] = {e.id: [] for e in engineers}

    for order in orders:                      # по порядку поступления
        pinned = locked.get(order.id)
        for engineer in engineers:            # первый подходящий по порядку
            if pinned is not None and engineer.id != pinned:
                continue
            if not engineer.can_do(order):
                continue
            candidate = sequences[engineer.id] + [order]
            route, _ = evaluate_sequence(engineer, candidate)
            if route is not None:
                sequences[engineer.id] = candidate
                routes[engineer.id] = route
                break

    plan = Plan(routes=list(routes.values()), strategy="baseline",
                solver_status="SEQUENTIAL",
                solve_seconds=round(time.perf_counter() - started, 3))
    return _finalize(plan, orders, engineers)



def solve_greedy(orders: list[Order], engineers: list[Engineer],
                 locked: dict[str, str] | None = None) -> Plan:
    """Жадное распределение с лучшей вставкой.

    Нужна как вторая точка отсчёта: базовый вариант из ТЗ намеренно наивен,
    и сравнивать оптимизатор только с ним было бы некорректно. Здесь заявки
    идут от срочных и ранних окон к поздним, каждая ставится в ту позицию
    маршрута, которая даёт минимальный прирост пробега, и предпочтение
    отдаётся уже задействованным исполнителям — чтобы не раздувать персонал.
    """
    started = time.perf_counter()
    locked = locked or {}
    by_id = {o.id: o for o in orders}
    routes = {e.id: Route(engineer_id=e.id) for e in engineers}
    engineer_by_id = {e.id: e for e in engineers}

    queue = sorted(
        orders,
        key=lambda o: (0 if o.priority == PRIORITY_URGENT else 1,
                       o.window_start, o.window_end, -o.duration_min),
    )

    for order in queue:
        best: tuple[float, str, Route] | None = None
        pinned = locked.get(order.id)
        for engineer in engineers:
            if pinned is not None and engineer.id != pinned:
                continue
            if not engineer.can_do(order):
                continue
            route = routes[engineer.id]
            for position in range(len(route.stops) + 1):
                ok, delta, new_route = insertion_cost(
                    engineer, route, by_id, order, position)
                if not ok:
                    continue
                # штраф за вывод нового исполнителя — метрика «персонал» важнее пробега
                score = delta + (ENGINEER_FIXED_COST / 1000.0 if not route.is_used else 0.0)
                if best is None or score < best[0]:
                    best = (score, engineer.id, new_route)
        if best is not None:
            routes[best[1]] = best[2]

    plan = Plan(routes=list(routes.values()), strategy="greedy",
                solver_status="GREEDY_INSERTION",
                solve_seconds=round(time.perf_counter() - started, 3))
    return _finalize(plan, orders, engineers)
