"""Сборка ответа с планом: одна форма для всех ручек."""
from __future__ import annotations

from dispatcher.api.deps import STORE, undo_labels
from dispatcher.domain import Plan
from dispatcher.domain.scenario import Scenario
from dispatcher.infrastructure import geo
from dispatcher.services.explain import explain_plan, explain_route
from dispatcher.services.impact import plan_risk
from dispatcher.services.planning.strategies import STRATEGY_TITLES, status_text


def plan_payload(scenario: Scenario, plan: Plan, metrics: dict,
                  extra: dict | None = None) -> dict:
    by_id = scenario.order_by_id
    # заявки, появившиеся после события, тоже должны попасть в ответ
    for route in plan.routes:
        for stop in route.stops:
            by_id.setdefault(stop.order_id, None)

    assignment: dict[str, str] = {}
    for route in plan.routes:
        for stop in route.stops:
            assignment[stop.order_id] = route.engineer_id

    payload = {
        "region": scenario.region_key,
        "region_name": scenario.region_name,
        "strategy": plan.strategy,
        "strategy_title": STRATEGY_TITLES.get(plan.strategy, plan.strategy),
        "solver_status": plan.solver_status,
        "solver_status_text": status_text(plan.solver_status),
        "solve_seconds": plan.solve_seconds,
        "locked": dict(getattr(STORE.current(scenario.region_key), "locked", {}) or {}),
        "undo": undo_labels(scenario.region_key),
        "metrics": metrics,
        "explanation": explain_plan(plan, all_orders(scenario, plan),
                                    all_engineers(scenario), metrics),
        "engineers": [
            {**engineer.to_dict(),
             "used": any(r.engineer_id == engineer.id and r.is_used
                         for r in plan.routes)}
            for engineer in all_engineers(scenario)
        ],
        "orders": [
            {**order.to_dict(), "assigned_to": assignment.get(order.id)}
            for order in all_orders(scenario, plan)
        ],
        "routes": [route.to_dict() for route in plan.routes if route.is_used],
        "unassigned": [u.to_dict() for u in plan.unassigned],
        "route_summaries": [
            explain_route(engineer, plan, all_orders(scenario, plan))
            for engineer in all_engineers(scenario)
            if any(r.engineer_id == engineer.id and r.is_used for r in plan.routes)
        ],
        # прогноз опозданий считается вместе с планом: он дешёвый, а в
        # интерфейсе риск нужен сразу рядом с каждым визитом
        "risk": plan_risk(plan, all_orders(scenario, plan), all_engineers(scenario)),
        "geo": geo_warning(all_orders(scenario, plan)),
    }
    if extra:
        payload.update(extra)
    return payload


def geo_warning(orders: list) -> dict:
    """Насколько можно доверять расстояниям в плане.

    Без прогона геокодера адрес разрешается в центроид района. Маршрут при
    этом остаётся корректным по навыкам, окнам и сменам, но километры и время
    в пути внутри района — оценка. Диспетчер должен видеть это до того,
    как отправит маршруты бригадам.
    """
    approx = [o.id for o in orders
              if getattr(o, "geocode_precision", "") == geo.PRECISION_APPROX]
    total = len(orders)
    share = len(approx) / total if total else 0.0
    if not approx:
        return {"approx_count": 0, "total": total, "share": 0.0,
                "level": "ok", "order_ids": [],
                "text": "Все адреса разрешены точно: расстояния и время в пути "
                        "посчитаны по реальным координатам."}
    return {
        "approx_count": len(approx),
        "total": total,
        "share": round(share, 3),
        # Пока точных координат меньше половины, километрам нельзя верить
        # даже приблизительно — это предупреждение, а не примечание.
        "level": "warn" if share >= 0.5 else "note",
        "order_ids": approx,
        "text": (f"У {len(approx)} из {total} заявок адрес не разрешён точно — "
                 f"взят центр района. Назначения, окна и смены от этого не "
                 f"страдают, но пробег и время в пути внутри района — оценка. "
                 f"Прогоните геокодер (scripts/geocode.py), чтобы цифры стали "
                 f"фактическими."),
    }


def all_orders(scenario: Scenario, plan: Plan) -> list:
    """Заявки сценария плюс добавленные событиями переплана."""
    state = STORE.current(scenario.region_key)
    if state and state.orders:
        return state.orders
    return scenario.orders


def all_engineers(scenario: Scenario) -> list:
    """Исполнители рабочего дня, а не исходного сценария.

    События смещают смены: выбывшему бригадиру смена обрезается, остальным
    двигается начало. Ответ, собранный по исходному сценарию, показал бы
    прежние смены и посчитал бы по ним запас прочности.
    """
    state = STORE.current(scenario.region_key)
    if state and state.engineers:
        return state.engineers
    return scenario.engineers
