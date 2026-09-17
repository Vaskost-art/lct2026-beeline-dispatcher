"""Метрики плана и сравнение вариантов.

Обязательные метрики ТЗ (п. 2.3):
  * количество уникальных исполнителей, которым назначена хотя бы одна заявка;
  * пробег по маршруту каждого исполнителя — отдельно и суммарно по плану.

Дополнительно считаем то, что помогает диспетчеру: долю назначенных заявок,
время в пути, загрузку смены и сравнение с фактическим распределением людей.
"""
from __future__ import annotations

from typing import TypedDict

from dispatcher.domain import Engineer, Order, Plan, hhmm


class EngineerRow(TypedDict):
    """Пробег и загрузка одного исполнителя."""

    engineer_id: str
    orders: int
    km: float
    travel_min: int
    work_min: int
    first_start: str
    last_end: str
    utilization: float


def plan_metrics(plan: Plan, orders: list[Order],
                 engineers: list[Engineer]) -> dict:
    engineer_by_id = {e.id: e for e in engineers}
    total = len(orders)

    per_engineer: list[EngineerRow] = []
    for route in plan.routes:
        if not route.is_used:
            continue
        engineer = engineer_by_id.get(route.engineer_id)
        # рабочее время без обеда: иначе загрузка занижена и маршрут,
        # упёршийся в потолок смены, выглядит как «есть куда добавить»
        shift_len = (engineer.work_end - engineer.shift_start) if engineer else 0
        busy = route.total_work_min + route.total_travel_min
        per_engineer.append({
            "engineer_id": route.engineer_id,
            "orders": len(route.stops),
            "km": round(route.total_km, 2),
            "travel_min": route.total_travel_min,
            "work_min": route.total_work_min,
            "first_start": hhmm(route.stops[0].start),
            "last_end": hhmm(route.stops[-1].end),
            "utilization": round(busy / shift_len, 3) if shift_len else 0.0,
        })
    per_engineer.sort(key=lambda r: -r["km"])

    assigned = plan.assigned_count
    travel_min = sum(r.total_travel_min for r in plan.routes)
    work_min = sum(r.total_work_min for r in plan.routes)

    return {
        "strategy": plan.strategy,
        # --- обязательные метрики ТЗ ---
        "used_engineers": plan.used_engineers,
        "total_km": round(plan.total_km, 2),
        "km_per_engineer": per_engineer,
        # --- вспомогательные ---
        "orders_total": total,
        "orders_assigned": assigned,
        "orders_unassigned": total - assigned,
        "assigned_share": round(assigned / total, 3) if total else 0.0,
        "engineers_available": len(engineers),
        "total_travel_min": travel_min,
        "total_work_min": work_min,
        "travel_share": round(travel_min / (travel_min + work_min), 3)
                        if (travel_min + work_min) else 0.0,
        "avg_km_per_order": round(plan.total_km / assigned, 2) if assigned else 0.0,
        "solver_status": plan.solver_status,
        "solve_seconds": plan.solve_seconds,
    }


def compare(candidate: dict[str, float], reference: dict[str, float]) -> dict:
    """Разница по обязательным метрикам: «наш план против точки отсчёта»."""
    def delta(key: str) -> float:
        return round(candidate[key] - reference[key], 2)

    def pct(key: str) -> float | None:
        base = reference[key]
        return round((candidate[key] - base) / base * 100, 1) if base else None

    return {
        "reference_strategy": reference["strategy"],
        "candidate_strategy": candidate["strategy"],
        "orders_assigned_delta": delta("orders_assigned"),
        "used_engineers_delta": delta("used_engineers"),
        "used_engineers_pct": pct("used_engineers"),
        "total_km_delta": delta("total_km"),
        "total_km_pct": pct("total_km"),
        # Суммарный пробег несопоставим между планами, закрывающими разное
        # число заявок: план, раздавший вдвое меньше работы, «экономит»
        # километры просто потому, что многого не делает. Сопоставима
        # удельная величина — километры на одну назначенную заявку.
        "km_per_order_delta": delta("avg_km_per_order"),
        "km_per_order_pct": pct("avg_km_per_order"),
    }
