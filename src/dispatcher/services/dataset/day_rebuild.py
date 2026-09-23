"""Подъём плана по снимку дня: маршруты пересчитываются тем же кодом, что строит план."""
from __future__ import annotations

from dispatcher.domain import Plan, Route
from dispatcher.services.dataset.day import DaySnapshot
from dispatcher.services.dataset.errors import DatasetError
from dispatcher.services.metrics import plan_metrics
from dispatcher.services.planning.reasons import diagnose
from dispatcher.services.routing import evaluate_sequence
from dispatcher.services.statuses import plannable


def rebuild(snapshot: DaySnapshot) -> tuple[Plan, dict[str, object], list[str]]:
    """Поднимает план по снимку, пересчитывая маршруты.

    Третьим значением возвращает заявки, которых в наборе не нашлось: день
    поднимется без них, но молчать об этом нельзя.
    """
    by_id = {order.id: order for order in snapshot.orders}
    engineer_by_id = {engineer.id: engineer for engineer in snapshot.engineers}
    routes: list[Route] = []
    lost: list[str] = []
    for engineer_id, sequence in snapshot.sequences.items():
        engineer = engineer_by_id.get(engineer_id)
        if engineer is None:
            continue
        known = [by_id[oid] for oid in sequence if oid in by_id]
        lost.extend(oid for oid in sequence if oid not in by_id)
        route, _ = evaluate_sequence(engineer, known)
        if route is None:
            raise DatasetError(
                f"Сохранённый маршрут «{engineer.name}» не проходит проверку "
                f"ограничений - запись не соответствует данным")
        routes.append(route)
    covered = {route.engineer_id for route in routes}
    routes.extend(Route(engineer_id=engineer.id) for engineer in snapshot.engineers
                  if engineer.id not in covered)

    plan = Plan(routes=routes, strategy=snapshot.strategy,
                solver_status=snapshot.solver_status)
    assigned = {stop.order_id for route in plan.routes for stop in route.stops}
    # Отменённые в дне остаются, но ни отказом, ни метрикой не считаются.
    working = plannable(snapshot.orders, snapshot.statuses)
    plan.unassigned = [diagnose(order, snapshot.engineers)
                       for order in working if order.id not in assigned]
    return plan, plan_metrics(plan, working, snapshot.engineers), lost
