"""Состояние заявок в течение смены и что из него следует.

Организаторы: факт выполнения или отмены фиксирует диспетчер со слов
бригады; закрытые заявки в планирование больше не включаются.
"""
from dispatcher.domain import (
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_ON_WAY,
    STATUS_SENT,
    Order,
    Plan,
    Route,
    Stop,
)
from dispatcher.services.statuses import (
    day_progress,
    frozen_by_status,
    is_closed,
    is_started,
    plannable,
    status_of,
)


def _order(order_id: str) -> Order:
    return Order(id=order_id, lat=55.7, lon=37.6, address="", district="",
                 duration_min=30, window_start=600, window_end=720,
                 priority="Обычная", required_skill="Локальные работы")


def _stop(order_id: str) -> Stop:
    return Stop(order_id=order_id, arrival=600, start=600, end=630,
                travel_min=10, travel_km=2.0, wait_min=0)


def _plan() -> Plan:
    return Plan(routes=[Route(engineer_id="Бригада 1",
                              stops=[_stop("1"), _stop("2"), _stop("3")])])


def test_unmarked_order_is_sent():
    """Заявка без отметки - наряд у бригады, работа не начата."""
    assert status_of("1", {}) == STATUS_SENT
    assert is_closed("1", {}) is False
    assert is_started("1", {}) is False


def test_closed_orders_leave_planning():
    orders = [_order("1"), _order("2")]
    marks = {"1": STATUS_CANCELLED}

    left = plannable(orders, marks)

    assert [o.id for o in left] == ["2"]


def test_done_order_stays_in_the_plan_but_is_not_replanned():
    """Завершённая заявка остаётся на месте: её уже сделали."""
    orders = [_order("1"), _order("2")]
    marks = {"1": STATUS_DONE}

    assert [o.id for o in plannable(orders, marks)] == ["1", "2"]
    assert frozen_by_status(_plan(), marks) == {"Бригада 1": ["1"]}


def test_freeze_covers_everything_before_the_touched_order():
    """Третья заявка выполнена - первые две уже не переставить.

    Иначе выполненная работа осталась бы на месте, а несделанная уехала бы
    после неё: маршрут перестал бы быть маршрутом.
    """
    marks = {"3": STATUS_DONE}

    assert frozen_by_status(_plan(), marks) == {"Бригада 1": ["1", "2", "3"]}


def test_cancelled_order_does_not_hold_the_prefix():
    """Отменённая заявка уходит из дня и никого не замораживает."""
    marks = {"1": STATUS_CANCELLED, "2": STATUS_ON_WAY}

    assert frozen_by_status(_plan(), marks) == {"Бригада 1": ["2"]}


def test_progress_counts_the_shift():
    orders = [_order(str(i)) for i in range(1, 6)]
    marks = {"1": STATUS_DONE, "2": STATUS_DONE, "3": STATUS_CANCELLED,
             "4": STATUS_ON_WAY}

    assert day_progress(orders, marks) == {
        "done": 2, "cancelled": 1, "in_progress": 1, "sent": 1}


def test_replan_keeps_the_finished_work_and_drops_the_cancelled(scenarios):
    """Сквозная проверка: отметки диспетчера доходят до перепланирования."""
    from dispatcher.domain import PRIORITY_URGENT
    from dispatcher.services.planning.optimizer import solve_optimized
    from dispatcher.services.replanning.apply import replan
    from dispatcher.services.replanning.events import KIND_URGENT, ReplanEvent

    scenario = scenarios["vostok"]
    plan = solve_optimized(scenario.orders, scenario.engineers, time_limit_sec=4)

    route = next(r for r in plan.routes if len(r.stops) >= 3)
    done_id = route.stops[0].order_id
    cancelled_id = route.stops[-1].order_id
    marks = {done_id: STATUS_DONE, cancelled_id: STATUS_CANCELLED}

    sample = scenario.orders[0]
    urgent = Order(id="ZZZ-9", lat=sample.lat, lon=sample.lon, address="",
                   district=sample.district, duration_min=40,
                   window_start=13 * 60, window_end=18 * 60,
                   priority=PRIORITY_URGENT,
                   required_skill=sample.required_skill)
    event = ReplanEvent(kind=KIND_URGENT, at=13 * 60, new_order=urgent)

    result = replan(scenario.orders, scenario.engineers, plan, event,
                    time_limit_sec=4, statuses=marks)

    placed = {stop.order_id: r.engineer_id
              for r in result.plan.routes for stop in r.stops}
    # Выполненная работа осталась у той же бригады и на том же месте.
    assert placed.get(done_id) == route.engineer_id
    # Отменённая заявка ушла из дня совсем: ни в маршрутах, ни в отказах.
    assert cancelled_id not in placed
    assert cancelled_id not in {u.order_id for u in result.plan.unassigned}
