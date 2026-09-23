"""Объяснение маршрута целиком и плана целиком."""
from __future__ import annotations

from dispatcher.domain import Engineer, Order, Plan, hhmm
from dispatcher.domain.text import decimal
from dispatcher.domain.text import plural as _plural


def explain_route(engineer: Engineer, plan: Plan,
                  orders: list[Order]) -> dict:
    """Краткая сводка по маршруту одного исполнителя."""
    by_id = {o.id: o for o in orders}
    route = next((r for r in plan.routes if r.engineer_id == engineer.id), None)
    if route is None or not route.stops:
        return {
            "engineer_id": engineer.id,
            "used": False,
            "summary": f"«{engineer.name}» - без заявок: план закрывается "
                       f"меньшим числом людей.",
            "steps": [],
        }

    steps = []
    for i, stop in enumerate(route.stops):
        order = by_id[stop.order_id]
        steps.append({
            "n": i + 1,
            "order_id": order.id,
            "district": order.district,
            "address": order.address,
            "type": order.type_hd,
            "arrival": hhmm(stop.arrival),
            "start": hhmm(stop.start),
            "end": hhmm(stop.end),
            "travel_km": round(stop.travel_km, 2),
            "travel_min": stop.travel_min,
            "wait_min": stop.wait_min,
            "priority": order.priority,
            "text": (f"{hhmm(stop.start)}–{hhmm(stop.end)} · {order.district}, "
                     f"{order.address} · {order.type_hd} "
                     f"({order.duration_min} мин, {decimal(stop.travel_km)} км в пути)"),
        })

    districts = sorted({by_id[s.order_id].district for s in route.stops})
    summary = (
        f"{engineer.vehicle}, смена {engineer.shift_text}. "
        f"В пути {route.total_travel_min} мин, на работах "
        f"{route.total_work_min} мин. "
        f"Районы: {', '.join(districts[:3])}"
        f"{' и другие' if len(districts) > 3 else ''}."
    )
    return {
        "engineer_id": engineer.id,
        "used": True,
        "summary": summary,
        "steps": steps,
    }


def explain_plan(plan: Plan, orders: list[Order], engineers: list[Engineer],
                 metrics: dict) -> dict:
    """Общее объяснение: что за план и за счёт чего он такой."""
    used = metrics["used_engineers"]
    available = metrics["engineers_available"]
    assigned = metrics["orders_assigned"]
    total = metrics["orders_total"]

    lines = [
        f"План закрывает {assigned} из {total} "
        f"{_plural(total, 'заявки', 'заявок', 'заявок')} силами {used} "
        f"{_plural(used, 'исполнителя', 'исполнителей', 'исполнителей')} "
        f"из {available} доступных.",
        f"Суммарный пробег - {decimal(metrics['total_km'])} км, "
        f"в среднем {decimal(metrics['avg_km_per_order'])} км на заявку. "
        f"Время в пути составляет {metrics['travel_share'] * 100:.0f}% "
        f"от общего времени работы бригад.",
    ]
    if plan.unassigned:
        by_reason: dict[str, int] = {}
        for u in plan.unassigned:
            by_reason[u.reason_text] = by_reason.get(u.reason_text, 0) + 1
        top = sorted(by_reason.items(), key=lambda kv: -kv[1])[:3]
        lines.append(
            "Не удалось назначить "
            f"{len(plan.unassigned)} "
            f"{_plural(len(plan.unassigned), 'заявку', 'заявки', 'заявок')}. "
            "Основные причины: " + " ".join(f"{text} (×{n})" for text, n in top)
        )
    else:
        lines.append("Все заявки распределены.")

    return {"lines": lines, "text": " ".join(lines)}
