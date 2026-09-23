"""Сборка ответа с планом: одна форма для всех ручек."""
from __future__ import annotations

from dispatcher.api.day import DayVersion
from dispatcher.api.deps import STORE, manual_labels, undo_labels
from dispatcher.domain import Plan, hhmm
from dispatcher.domain.scenario import Scenario
from dispatcher.infrastructure import geo
from dispatcher.services.equipment import issued_rows, pickup_list
from dispatcher.services.explain import explain_plan, explain_route
from dispatcher.services.impact import plan_risk
from dispatcher.services.planning.baseline import solve_greedy
from dispatcher.services.planning.shortfall import crews_shortfall
from dispatcher.services.planning.strategies import STRATEGY_TITLES, status_text
from dispatcher.services.statuses import day_progress


def plan_payload(scenario: Scenario, plan: Plan, metrics: dict,
                  extra: dict | None = None, version: DayVersion | None = None) -> dict:
    # Предпросмотр передаёт свою версию явно: подкладывать её в историю дня
    # на время ответа значило бы дать параллельной правке снять не ту версию.
    current = version or STORE.current(scenario.region_key)
    issued = current.issued if current else {}
    statuses = current.statuses if current else {}
    # Заявки и бригады берутся у той же версии: у предпросмотра новой заявки
    # их нет в текущем дне, и ответ падал на объяснении её маршрута.
    orders = current.orders if current and current.orders else scenario.orders
    engineers = current.engineers if current and current.engineers else scenario.engineers
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
        "locked": dict(current.locked) if current else {},
        "undo": undo_labels(scenario.region_key),
        # Отдельно от истории: пересчёт откатывается шагом назад, но
        # «что потеряется при сборке заново» - это только решения человека.
        "manual_changes": manual_labels(scenario.region_key),
        "metrics": metrics,
        "explanation": explain_plan(plan, orders,
                                    engineers, metrics),
        "engineers": [
            {**engineer.to_dict(),
             "used": any(r.engineer_id == engineer.id and r.is_used
                         for r in plan.routes)}
            for engineer in engineers
        ],
        "orders": [
            {**order.to_dict(), "assigned_to": assignment.get(order.id)}
            for order in orders
        ],
        "routes": [route.to_dict() for route in plan.routes if route.is_used],
        "unassigned": [u.to_dict() for u in plan.unassigned],
        "route_summaries": [
            explain_route(engineer, plan, orders)
            for engineer in engineers
            if any(r.engineer_id == engineer.id and r.is_used for r in plan.routes)
        ],
        # прогноз опозданий считается вместе с планом: он дешёвый, а в
        # интерфейсе риск нужен сразу рядом с каждым визитом
        "risk": plan_risk(plan, orders, engineers),
        # Ведомость показывает выданное, а не расчёт по текущему плану:
        # оборудование бригада получила утром с запасом, и экран обязан
        # совпадать с тем, по чему система решает, кому отдать заявку.
        "pickup": (issued_rows(issued) if issued
                   else pickup_list(plan, orders)),
        "shortfall": crews_shortfall(
            plan, orders, solve_greedy,
            scenario.office_lat, scenario.office_lon, scenario.office_address,
            current.clock if current else 0),
        "geo": geo_warning(orders),
        #: Что с заявками прямо сейчас и сколько уже закрыто: ход смены
        #: виден диспетчеру, а не выводится им из маршрутов.
        "statuses": dict(statuses),
        "progress": day_progress(orders, statuses),
        # Время смены: момент последнего применённого события. Форма события
        # начинает с него, а раньше него сервис событие не примет.
        "clock": hhmm(current.clock) if current and current.clock else "",
    }
    if extra:
        payload.update(extra)
    return payload


def geo_warning(orders: list) -> dict:
    """Насколько можно доверять расстояниям в плане.

    Без прогона геокодера адрес разрешается в центроид района. Маршрут при
    этом остаётся корректным по навыкам, окнам и сменам, но километры и время
    в пути внутри района - оценка. Диспетчер должен видеть это до того,
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
        # даже приблизительно - это предупреждение, а не примечание.
        "level": "warn" if share >= 0.5 else "note",
        "order_ids": approx,
        "text": (f"У {len(approx)} из {total} заявок адрес не разрешён точно - "
                 f"взят центр района. Назначения, окна и смены от этого не "
                 f"страдают, но пробег и время в пути внутри района - оценка. "
                 f"Цифры станут точными, если в файле уточнить адреса."),
    }
