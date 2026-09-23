"""Что будет с планом, если работы затянутся."""
from __future__ import annotations

from dispatcher.domain import Engineer, Order, Plan
from dispatcher.services.risk import (
    DELAY_CAP_MIN,
    RISK_HIGH,
    RISK_HIGH_BELOW,
    RISK_LOW,
    RISK_MEDIUM,
    RISK_MEDIUM_BELOW,
    route_risk,
    simulate,
)


def overrun_impact(plan: Plan, orders: list[Order], engineers: list[Engineer],
                   overrun_per_job: int) -> dict:
    """Что будет, если каждая работа в плане затянется на N минут."""
    by_id = {o.id: o for o in orders}
    engineer_by_id = {e.id: e for e in engineers}
    broken: list[dict] = []

    for route in plan.routes:
        if not route.stops:
            continue
        engineer = engineer_by_id.get(route.engineer_id)
        if engineer is None:
            continue
        sequence = [by_id[s.order_id] for s in route.stops
                    if s.order_id in by_id]
        index = simulate(engineer, sequence, overrun_per_job=overrun_per_job)
        if index is None:
            continue
        # всё, начиная с точки срыва, считаем под угрозой: дальше маршрут
        # уже не выполняется по правилам ТЗ
        for order in sequence[index:]:
            broken.append({
                "order_id": order.id,
                "engineer_id": engineer.id,
                "window": order.window_text,
                "district": order.district,
                "priority": order.priority,
            })

    urgent = sum(1 for b in broken if b["priority"] == "Срочная")
    engineers_hit = len({b["engineer_id"] for b in broken})
    total = plan.assigned_count

    if not broken:
        text = (f"Если каждая работа затянется на {overrun_per_job} мин, план "
                f"всё равно выполним: ни одна заявка не выпадает из окна и "
                f"ни один маршрут не выходит за смену.")
    else:
        text = (f"Если каждая работа затянется на {overrun_per_job} мин, "
                f"под угрозой {len(broken)} из {total} назначенных заявок "
                f"у {engineers_hit} исполнителей"
                + (f", в том числе {urgent} срочных." if urgent else "."))

    return {
        "overrun_per_job": overrun_per_job,
        "broken": broken,
        "broken_count": len(broken),
        "urgent_count": urgent,
        "engineers_affected": engineers_hit,
        "assigned_total": total,
        "text": text,
    }


def plan_risk(plan: Plan, orders: list[Order], engineers: list[Engineer],
              overruns: tuple[int, ...] = (10, 20, 30)) -> dict:
    """Полный отчёт о рисках плана."""
    by_id = {o.id: o for o in orders}
    engineer_by_id = {e.id: e for e in engineers}

    routes = []
    for route in plan.routes:
        if not route.stops:
            continue
        engineer = engineer_by_id.get(route.engineer_id)
        if engineer is None:
            continue
        sequence = [by_id[s.order_id] for s in route.stops if s.order_id in by_id]
        routes.append(route_risk(engineer, sequence))

    routes.sort(key=lambda r: r.get("tolerance_min", DELAY_CAP_MIN))

    stop_risks = [s for r in routes for s in r["stops"]]
    by_risk = {RISK_HIGH: 0, RISK_MEDIUM: 0, RISK_LOW: 0}
    for stop in stop_risks:
        by_risk[stop["risk"]] += 1

    weakest = routes[0] if routes else None
    scenarios = [overrun_impact(plan, orders, engineers, minutes)
                 for minutes in overruns]

    summary_parts = []
    if weakest:
        summary_parts.append(
            f"Самый хрупкий маршрут - «{weakest['engineer_id']}»: "
            f"выдержит задержку до {weakest['tolerance_min']} мин.")
    if by_risk[RISK_HIGH]:
        summary_parts.append(
            f"Визитов с высоким риском опоздания (запас меньше "
            f"{RISK_HIGH_BELOW} мин): {by_risk[RISK_HIGH]}.")
    else:
        summary_parts.append(
            f"Визитов с высоким риском нет: у каждого запас не меньше "
            f"{RISK_HIGH_BELOW} мин.")
    if scenarios:
        summary_parts.append(scenarios[0]["text"])

    return {
        "routes": routes,
        "by_risk": by_risk,
        "weakest_route": weakest,
        "scenarios": scenarios,
        "thresholds": {"high_below": RISK_HIGH_BELOW,
                       "medium_below": RISK_MEDIUM_BELOW,
                       "cap": DELAY_CAP_MIN},
        "summary": " ".join(summary_parts),
    }
