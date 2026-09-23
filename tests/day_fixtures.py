"""Заготовки дня для тестов событий: одна бригада, плотные визиты.

День собран под сам проверяемый выбор, а не взят из боевых данных: там у
кого-нибудь почти всегда есть свободный вечер, и тест ничего бы не показал.
"""
from dispatcher.domain import (
    PRIORITY_NORMAL,
    SKILL_LOCAL,
    Engineer,
    Order,
    Plan,
)
from dispatcher.domain.catalog import VEHICLE_CAR
from dispatcher.services.replanning.apply import replan
from dispatcher.services.replanning.events import KIND_URGENT, ReplanEvent
from dispatcher.services.routing import evaluate_sequence

LAT, LON = 55.75, 37.62
EVENT_AT = 12 * 60


def order_at(order_id: str, start: int, duration: int, priority: str = PRIORITY_NORMAL,
             window: int = 60) -> Order:
    """Заявка в общей точке с окном `window` минут от `start`."""
    return Order(id=order_id, lat=LAT, lon=LON, address="", district="",
                 duration_min=duration, window_start=start, window_end=start + window,
                 priority=priority, required_skill=SKILL_LOCAL)


def one_crew_day() -> tuple[list[Engineer], list[Order], Plan]:
    """Визиты 9:00, 11:00, 13:00, 15:00 по полтора часа; смена до 17:00."""
    crew = Engineer(id="crew", name="Бригада", lat=LAT, lon=LON, start_address="",
                    shift_start=9 * 60, shift_end=17 * 60, skills=[SKILL_LOCAL],
                    vehicle=VEHICLE_CAR)
    orders = [order_at(f"o{hour}", hour * 60, 90) for hour in (9, 11, 13, 15)]
    route, _ = evaluate_sequence(crew, orders)
    assert route is not None
    return [crew], orders, Plan(routes=[route])


def starts(plan: Plan, ids: set[str]) -> dict[str, int]:
    """Начало визита по каждой из заявок `ids`."""
    return {stop.order_id: stop.start for route in plan.routes
            for stop in route.stops if stop.order_id in ids}


def replan_one_crew(new: Order, mode: str = "minimal"):
    """Новая заявка в день одной бригады: исходный план и результат."""
    engineers, orders, plan = one_crew_day()
    event = ReplanEvent(kind=KIND_URGENT, at=EVENT_AT, new_order=new)
    return plan, replan(orders, engineers, plan, event, mode=mode, time_limit_sec=4)
