"""События дня на вырожденных наборах: все ветки перепланирования."""
from __future__ import annotations

import traceback
from dataclasses import replace

from stress_checks import TIME_LIMIT, check_invariants, fail

from dispatcher.domain import Engineer, Order, Plan, catalog
from dispatcher.services.replanning.apply import replan
from dispatcher.services.replanning.events import (
    KIND_CANCEL,
    KIND_DELAYED,
    KIND_UNAVAILABLE,
    KIND_URGENT,
    ReplanEvent,
    make_new_order,
)
from dispatcher.services.replanning.repair import MODE_FULL, MODE_MINIMAL


def run_events(name: str, orders: list[Order], engineers: list[Engineer],
               plan: Plan) -> None:
    """Все ветки перепланирования, включая граничные моменты времени."""
    if not orders or not engineers:
        return

    assigned = [s.order_id for r in plan.routes for s in r.stops]
    any_order = assigned[0] if assigned else orders[0].id
    busiest = max(plan.routes, key=lambda r: len(r.stops)).engineer_id \
        if plan.routes else engineers[0].id
    idle = next((r.engineer_id for r in plan.routes if not r.stops), None)

    urgent = make_new_order(
        order_id="STRESS-URGENT", lat=orders[0].lat, lon=orders[0].lon,
        address="Проверочная точка", district=orders[0].district,
        duration_min=60, window_start=14 * 60, window_end=16 * 60,
        required_skill=orders[0].required_skill)

    urgent_past = replace(urgent, id="STRESS-PAST",
                          window_start=1, window_end=2)
    urgent_no_skill = replace(urgent, id="STRESS-NOSKILL",
                              required_skill=catalog.SKILL_EMERGENCY,
                              required_vehicle=catalog.VEHICLE_BIKE)

    events = [
        ("срочная днём", ReplanEvent(KIND_URGENT, 13 * 60, new_order=urgent)),
        ("срочная в 00:00", ReplanEvent(KIND_URGENT, 0, new_order=urgent)),
        ("срочная в 23:59", ReplanEvent(KIND_URGENT, 23 * 60 + 59, new_order=urgent)),
        ("срочная с окном в прошлом",
         ReplanEvent(KIND_URGENT, 13 * 60, new_order=urgent_past)),
        ("срочная, которую некому взять",
         ReplanEvent(KIND_URGENT, 13 * 60, new_order=urgent_no_skill)),
        ("отмена назначенной", ReplanEvent(KIND_CANCEL, 12 * 60, order_id=any_order)),
        ("отмена в 00:00", ReplanEvent(KIND_CANCEL, 0, order_id=orders[0].id)),
        ("отмена в 23:59",
         ReplanEvent(KIND_CANCEL, 23 * 60 + 59, order_id=orders[0].id)),
        ("выбыл загруженный", ReplanEvent(KIND_UNAVAILABLE, 13 * 60,
                                          engineer_id=busiest)),
        ("выбыл в 00:00", ReplanEvent(KIND_UNAVAILABLE, 0, engineer_id=busiest)),
        ("выбыл в 23:59", ReplanEvent(KIND_UNAVAILABLE, 23 * 60 + 59,
                                      engineer_id=busiest)),
    ]
    if idle:
        events.append(("выбыл незанятый",
                       ReplanEvent(KIND_UNAVAILABLE, 13 * 60, engineer_id=idle)))

    # Задержка бригады: от минимальной до заведомо съедающей весь день,
    # и на границах суток - там задержка либо не к чему применяться,
    # либо применяется к уже закрытой смене.
    events += [
        ("задержка 5 мин", ReplanEvent(KIND_DELAYED, 13 * 60,
                                       engineer_id=busiest, delay_min=5)),
        ("задержка 90 мин", ReplanEvent(KIND_DELAYED, 13 * 60,
                                        engineer_id=busiest, delay_min=90)),
        ("задержка на весь день", ReplanEvent(KIND_DELAYED, 13 * 60,
                                              engineer_id=busiest, delay_min=480)),
        ("задержка в 00:00", ReplanEvent(KIND_DELAYED, 0,
                                         engineer_id=busiest, delay_min=60)),
        ("задержка в 23:59", ReplanEvent(KIND_DELAYED, 23 * 60 + 59,
                                         engineer_id=busiest, delay_min=60)),
    ]
    if idle:
        events.append(("задержка незанятого",
                       ReplanEvent(KIND_DELAYED, 13 * 60,
                                   engineer_id=idle, delay_min=60)))

    for title, event in events:
        for mode in (MODE_MINIMAL, MODE_FULL):
            where = f"{name} / {title} / {mode}"
            try:
                result = replan(orders, engineers, plan, event, mode=mode,
                                time_limit_sec=TIME_LIMIT)
            except Exception as exc:
                fail(where, f"ИСКЛЮЧЕНИЕ {type(exc).__name__}: {exc}")
                traceback.print_exc()
                continue
            check_invariants(where, result.plan, result.orders, result.engineers)
            if not result.narrative:
                fail(where, "переплан не объяснил, что произошло")


def run_chain(name: str, orders: list[Order], engineers: list[Engineer],
              plan: Plan) -> None:
    """Цепочка событий: каждое следующее считается от применённого предыдущего."""
    if len(orders) < 3 or len(engineers) < 2:
        return
    current_orders, current_engineers, current = orders, engineers, plan
    for step in range(1, 6):
        assigned = [s.order_id for r in current.routes for s in r.stops]
        if not assigned:
            break
        event = ReplanEvent(KIND_CANCEL, (9 + step) * 60, order_id=assigned[0])
        where = f"{name} / цепочка, шаг {step}"
        try:
            result = replan(current_orders, current_engineers, current, event,
                            mode=MODE_MINIMAL, time_limit_sec=TIME_LIMIT)
        except Exception as exc:
            fail(where, f"ИСКЛЮЧЕНИЕ {type(exc).__name__}: {exc}")
            return
        check_invariants(where, result.plan, result.orders, result.engineers)
        current_orders, current_engineers, current = (
            result.orders, result.engineers, result.plan)
