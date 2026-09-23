"""Инварианты стресс-теста: то, что обязано выполняться для ЛЮБОГО плана.

Счётчик проверок и список нарушений общие на весь прогон: их читает
`stress.py` в конце.
"""
from __future__ import annotations

import os

from dispatcher.domain import Engineer, Order, Plan, hhmm
from dispatcher.services.impact import plan_risk
from dispatcher.services.metrics import plan_metrics
from dispatcher.services.validate import validate

TIME_LIMIT = int(os.environ.get("STRESS_TIME_LIMIT", "3"))

problems: list[str] = []
checks_done = 0


def fail(where: str, what: str) -> None:
    problems.append(f"{where}: {what}")
    print(f"      ✗ {what}")


# --------------------------------------------------------------------------
#  Инварианты - то, что обязано выполняться для ЛЮБОГО плана
# --------------------------------------------------------------------------

def check_invariants(where: str, plan: Plan, orders: list[Order],
                     engineers: list[Engineer]) -> None:
    global checks_done
    checks_done += 1

    order_ids = {o.id for o in orders}
    by_id = {o.id: o for o in orders}
    assigned: list[str] = []
    for route in plan.routes:
        assigned.extend(s.order_id for s in route.stops)

    # 1. Никаких дублей в назначениях
    if len(assigned) != len(set(assigned)):
        dupes = [x for x in set(assigned) if assigned.count(x) > 1]
        fail(where, f"заявка назначена дважды: {dupes[:3]}")

    # 2. Назначены только существующие заявки
    unknown = set(assigned) - order_ids
    if unknown:
        fail(where, f"назначены несуществующие заявки: {sorted(unknown)[:3]}")

    # 3. Назначенное и неназначенное не пересекаются
    unassigned_ids = {u.order_id for u in plan.unassigned}
    both = set(assigned) & unassigned_ids
    if both:
        fail(where, f"заявка одновременно назначена и не назначена: {sorted(both)[:3]}")

    # 4. Вместе они покрывают весь набор
    covered = set(assigned) | unassigned_ids
    if covered != order_ids:
        missing = order_ids - covered
        extra = covered - order_ids
        if missing:
            fail(where, f"заявки потерялись, их нет ни в плане, ни в отказах: "
                        f"{sorted(missing)[:3]}")
        if extra:
            fail(where, f"в отказах есть посторонние заявки: {sorted(extra)[:3]}")

    # 5. У каждого отказа есть причина словами
    for u in plan.unassigned:
        if not (u.reason_text or "").strip():
            fail(where, f"у заявки {u.order_id} отказ без причины")
            break
        if not (u.reason or "").strip():
            fail(where, f"у заявки {u.order_id} отказ без кода причины")
            break

    # 6. Времена внутри маршрута монотонны и неотрицательны
    for route in plan.routes:
        previous_end = None
        for stop in route.stops:
            if stop.start > stop.end:
                fail(where, f"{route.engineer_id}/{stop.order_id}: "
                            f"начало {hhmm(stop.start)} позже конца {hhmm(stop.end)}")
                break
            if stop.arrival > stop.start:
                fail(where, f"{route.engineer_id}/{stop.order_id}: "
                            f"работы начаты раньше прибытия")
                break
            if stop.travel_km < 0 or stop.travel_min < 0 or stop.wait_min < 0:
                fail(where, f"{route.engineer_id}/{stop.order_id}: "
                            f"отрицательные пробег, время в пути или ожидание")
                break
            if previous_end is not None and stop.arrival < previous_end:
                fail(where, f"{route.engineer_id}/{stop.order_id}: "
                            f"выехал раньше, чем закончил предыдущую заявку")
                break
            order = by_id.get(stop.order_id)
            if order and stop.end - stop.start != order.duration_min:
                fail(where, f"{route.engineer_id}/{stop.order_id}: "
                            f"длительность работ не совпадает с заявкой")
                break
            previous_end = stop.end

    # 7. Метрики не противоречат плану
    if plan.total_km < -1e-9:
        fail(where, "суммарный пробег отрицательный")
    if plan.used_engineers > len(engineers):
        fail(where, "задействовано больше исполнителей, чем есть")

    # 8. Независимый аудит ограничений
    report = validate(plan, orders, engineers)
    if not report.ok:
        first = report.violations[0]
        fail(where, f"аудит: {first.rule} - {first.text}")

    # 9. Метрики считаются без исключений
    try:
        plan_metrics(plan, orders, engineers)
    except Exception as exc:
        fail(where, f"метрики не посчитались: {exc}")

    # 10. Прогноз опозданий считается без исключений
    try:
        plan_risk(plan, orders, engineers)
    except Exception as exc:
        fail(where, f"прогноз опозданий не посчитался: {exc}")
