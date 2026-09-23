"""Нехватка бригад считается от плана на экране.

Раньше её считал быстрый расчёт с нуля: на Востоке экран одновременно
показывал 66 из 66 заявок и «нужно ещё 2 бригады».
"""
from day_fixtures import LAT, LON, order_at

from dispatcher.domain import Plan, Unassigned
from dispatcher.services.planning.baseline import solve_greedy
from dispatcher.services.planning.shortfall import crews_shortfall


def test_full_plan_needs_no_more_crews():
    orders = [order_at("a", 10 * 60, 60)]

    answer = crews_shortfall(Plan(routes=[]), orders, solve_greedy, LAT, LON, "")

    assert answer["missing"] == 0
    assert answer["profiles"] == []


def test_left_order_gets_a_new_crew_named_as_new():
    orders = [order_at("a", 10 * 60, 60)]
    plan = Plan(routes=[], unassigned=[Unassigned("a", "no_capacity", "")])

    answer = crews_shortfall(plan, orders, solve_greedy, LAT, LON, "")

    assert answer["missing"] == 1
    assert answer["still_unassigned"] == 0
    assert answer["assigned"] == 1
