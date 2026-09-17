"""Характеризационный тест: фиксирует текущий результат планирования.

Тест ничего не улучшает. Он доказывает, что переезд модулей по слоям не
изменил ни одного числа.
"""
import json
import os

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN = os.path.join(HERE, "data", "characterization.json")


def _snapshot(scenario) -> dict:
    from metrics import plan_metrics
    from solver import solve_baseline, solve_greedy

    out = {}
    for name, solve in (("baseline", solve_baseline), ("greedy", solve_greedy)):
        plan = solve(scenario.orders, scenario.engineers)
        metrics = plan_metrics(plan, scenario.orders, scenario.engineers)
        out[name] = {
            "assigned": metrics["orders_assigned"],
            "unassigned": metrics["orders_unassigned"],
            "used_engineers": metrics["used_engineers"],
            "total_km": round(metrics["total_km"], 3),
        }
    return out


def test_planning_result_unchanged(scenarios):
    actual = {key: _snapshot(scenario) for key, scenario in sorted(scenarios.items())}

    if not os.path.exists(GOLDEN):
        os.makedirs(os.path.dirname(GOLDEN), exist_ok=True)
        with open(GOLDEN, "w", encoding="utf-8") as fh:
            json.dump(actual, fh, ensure_ascii=False, indent=2, sort_keys=True)
        pytest.skip("эталон создан, повторный запуск сравнит с ним")

    with open(GOLDEN, encoding="utf-8") as fh:
        expected = json.load(fh)
    assert actual == expected


def test_every_order_is_either_routed_or_refused(scenarios):
    """Заявка не имеет права потеряться между маршрутами и отказами."""
    from solver import solve_greedy

    for scenario in scenarios.values():
        plan = solve_greedy(scenario.orders, scenario.engineers)
        routed = {stop.order_id for route in plan.routes for stop in route.stops}
        refused = {u.order_id for u in plan.unassigned}
        assert routed.isdisjoint(refused)
        assert routed | refused == {o.id for o in scenario.orders}


def test_plans_pass_independent_validation(scenarios):
    """Готовый план проходит независимую проверку ограничений."""
    from solver import solve_baseline, solve_greedy
    from validate import validate

    for scenario in scenarios.values():
        for solve in (solve_baseline, solve_greedy):
            plan = solve(scenario.orders, scenario.engineers)
            report = validate(plan, scenario.orders, scenario.engineers)
            assert report.ok, report.by_rule()
