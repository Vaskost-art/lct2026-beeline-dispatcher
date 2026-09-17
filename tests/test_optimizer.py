"""Оптимизатор: проверяем свойства решения, а не числа.

Расчёт ограничен временем, поэтому маршруты от прогона к прогону отличаются.
Сравнивать их с эталоном нельзя, а вот требовать соблюдения правил можно.
"""
import pytest

TIME_LIMIT_SEC = 5


@pytest.fixture(scope="module")
def optimized(scenarios):
    from dispatcher.services.planning.optimizer import solve_optimized

    return {
        key: (scenario, solve_optimized(scenario.orders, scenario.engineers,
                                        time_limit_sec=TIME_LIMIT_SEC))
        for key, scenario in scenarios.items()
    }


def test_plan_passes_independent_validation(optimized):
    from dispatcher.services.validate import validate

    for scenario, plan in optimized.values():
        report = validate(plan, scenario.orders, scenario.engineers)
        assert report.ok, report.by_rule()


def test_no_order_is_lost(optimized):
    """Заявка либо в маршруте, либо в отказах с причиной. Третьего нет."""
    for scenario, plan in optimized.values():
        routed = {stop.order_id for route in plan.routes for stop in route.stops}
        refused = {u.order_id for u in plan.unassigned}
        assert routed.isdisjoint(refused)
        assert routed | refused == {o.id for o in scenario.orders}
        assert all(u.reason for u in plan.unassigned)


def test_status_is_explained_to_the_dispatcher(optimized):
    """У любого исхода расчёта есть текст, который читает человек."""
    from dispatcher.services.planning.strategies import status_text

    for _, plan in optimized.values():
        described = status_text(plan.solver_status)
        assert described["text"]
        assert described["level"] in {"ok", "warn", "error"}


def test_optimizer_beats_the_baseline(optimized):
    """Оптимизатор обязан назначать не меньше заявок, чем вариант из ТЗ."""
    from dispatcher.services.planning.baseline import solve_baseline

    for scenario, plan in optimized.values():
        base = solve_baseline(scenario.orders, scenario.engineers)
        assert plan.assigned_count >= base.assigned_count
