"""Перепланирование дня: каждое событие в каждом режиме.

Здесь однажды терялся целый день работы: после события «исполнитель
недоступен» из плана исчезало то, что бригады уже выполнили. Поэтому
сохранность выполненной части проверяется отдельно и явно.
"""
import pytest

TIME_LIMIT_SEC = 4
EVENT_AT = 13 * 60


@pytest.fixture(scope="module")
def day(scenarios):
    """Участок и построенный на нём план."""
    from dispatcher.services.planning.optimizer import solve_optimized

    scenario = scenarios["vostok"]
    plan = solve_optimized(scenario.orders, scenario.engineers,
                           time_limit_sec=TIME_LIMIT_SEC)
    return scenario, plan


def _events(plan):
    from dispatcher.services.replanning.events import KIND_CANCEL, KIND_DELAYED, KIND_UNAVAILABLE

    route = next(r for r in plan.routes if r.stops)
    return [
        (KIND_CANCEL, {"order_id": route.stops[-1].order_id}),
        (KIND_UNAVAILABLE, {"engineer_id": route.engineer_id}),
        (KIND_DELAYED, {"engineer_id": route.engineer_id, "delay_min": 45}),
    ]


def _replans(day):
    from dispatcher.services.replanning.apply import replan
    from dispatcher.services.replanning.events import ReplanEvent
    from dispatcher.services.replanning.repair import MODE_FULL, MODE_MINIMAL

    scenario, plan = day
    for kind, extra in _events(plan):
        for mode in (MODE_MINIMAL, MODE_FULL):
            event = ReplanEvent(kind=kind, at=EVENT_AT, **extra)
            yield kind, mode, plan, replan(scenario.orders, scenario.engineers,
                                           plan, event, mode=mode,
                                           time_limit_sec=TIME_LIMIT_SEC)


def test_result_passes_independent_validation(day):
    from dispatcher.services.validate import validate

    for kind, mode, _, result in _replans(day):
        report = validate(result.plan, result.orders, result.engineers)
        assert report.ok, f"{kind}/{mode}: {report.by_rule()}"


def test_completed_work_survives_the_event(day):
    """Всё, что бригада успела сделать до события, остаётся в плане."""
    for kind, mode, before, result in _replans(day):
        done_before = {
            stop.order_id
            for route in before.routes
            for stop in route.stops
            if stop.end <= EVENT_AT
        }
        after = {stop.order_id for route in result.plan.routes for stop in route.stops}
        cancelled = {
            u.order_id for u in result.plan.unassigned
        } if kind == "cancel_order" else set()
        lost = done_before - after - cancelled
        assert not lost, f"{kind}/{mode}: потеряно выполненное {sorted(lost)}"


def test_no_order_is_lost(day):
    for kind, mode, _, result in _replans(day):
        routed = {stop.order_id for route in result.plan.routes for stop in route.stops}
        refused = {u.order_id for u in result.plan.unassigned}
        assert routed.isdisjoint(refused), f"{kind}/{mode}"
        assert routed | refused == {o.id for o in result.orders}, f"{kind}/{mode}"
