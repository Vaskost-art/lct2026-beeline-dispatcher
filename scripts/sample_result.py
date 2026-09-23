"""Пример результата в формате ТЗ (п. 2.4.2) для тестового набора."""
from __future__ import annotations

from dispatcher.domain import Plan, hhmm
from dispatcher.domain.scenario import Scenario


def result_json(scenario: Scenario, plan: Plan, metrics: dict) -> dict:
    """Маршруты, назначения, отказы и метрики плана по-русски, как в ТЗ."""
    by_id = scenario.order_by_id
    assignment = {s.order_id: r.engineer_id
                  for r in plan.routes for s in r.stops}
    return {
        "район": scenario.region_name,
        "стратегия": plan.strategy,
        "исполнители": [
            {
                "исполнитель": route.engineer_id,
                "пробег_км": round(route.total_km, 2),
                "время_в_пути_мин": route.total_travel_min,
                "маршрут": [
                    {
                        "порядок": i + 1,
                        "заявка": stop.order_id,
                        "адрес": by_id[stop.order_id].address,
                        "прибытие": hhmm(stop.arrival),
                        "начало_работ": hhmm(stop.start),
                        "окончание": hhmm(stop.end),
                        "пробег_до_точки_км": round(stop.travel_km, 2),
                    }
                    for i, stop in enumerate(route.stops)
                ],
            }
            for route in plan.routes if route.is_used
        ],
        "заявки": [
            {"заявка": o.id, "исполнитель": assignment.get(o.id),
             "статус": "назначена" if o.id in assignment else "не назначена"}
            for o in scenario.orders
        ],
        "не_назначены": [
            {"заявка": u.order_id, "причина": u.reason_text}
            for u in plan.unassigned
        ],
        "метрики": {
            "задействовано_исполнителей": metrics["used_engineers"],
            "доступно_исполнителей": metrics["engineers_available"],
            "пробег_по_исполнителям": {row["engineer_id"]: row["km"]
                                       for row in metrics["km_per_engineer"]},
            "суммарный_пробег_км": metrics["total_km"],
            "назначено_заявок": metrics["orders_assigned"],
            "всего_заявок": metrics["orders_total"],
        },
    }
