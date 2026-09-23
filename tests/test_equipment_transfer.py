"""Выдача и передача оборудования днём.

Организаторы: оборудование выдаётся утром, но в течение дня может
передаваться между инженерами. Отдаётся только свободное.
"""
import pytest
from bag_fixtures import bag_day, bag_order

from dispatcher.domain.equipment import ROUTER, SPARE_PER_ITEM, TV_BOX
from dispatcher.services.equipment import issued_items, missing_for


def test_refusal_names_the_device_in_a_readable_form():
    """«нет роутера», а не «нет роутер»: отказ читает человек."""
    from dispatcher.domain.equipment import SPEAKER
    from dispatcher.services.equipment import name_listing

    assert name_listing([ROUTER]) == "роутера"
    assert name_listing([ROUTER, TV_BOX]) == "роутера и приставки"
    assert name_listing([ROUTER, ROUTER, SPEAKER]) == "роутера и колонки"


def test_issued_sheet_shows_what_was_given_out():
    """Ведомость показывает выданное с запасом, а не расчёт по плану."""
    from dispatcher.services.equipment import issued_rows

    plan, orders = bag_day()
    rows = issued_rows(issued_items(plan, orders))

    assert len(rows) == 1
    row = rows[0]
    assert row["engineer_id"] == "Бригада 1"
    assert row["items"][ROUTER] == 2 + SPARE_PER_ITEM
    assert row["total"] == sum(row["items"].values())


def test_transfer_moves_a_free_device():
    """Свободное устройство уходит соседу: заказчик это разрешил."""
    from dispatcher.services.equipment import transfer

    plan, orders = bag_day()
    issued = issued_items(plan, orders)      # Бригада 1: 3 роутера, 2 под заявки

    updated = transfer(issued, plan, orders, "Бригада 1", "Бригада 2", ROUTER, 1)

    assert updated["Бригада 1"][ROUTER] == 2
    assert updated["Бригада 2"][ROUTER] == 1
    # Ведомость не меняется на месте: прежняя версия дня остаётся целой.
    assert issued["Бригада 1"][ROUTER] == 2 + SPARE_PER_ITEM


def test_transfer_does_not_take_what_is_promised_to_clients():
    """Отдать можно только свободное: под свои заявки устройство остаётся."""
    from dispatcher.services.equipment import transfer

    plan, orders = bag_day()
    issued = issued_items(plan, orders)

    with pytest.raises(ValueError, match="свободно"):
        transfer(issued, plan, orders, "Бригада 1", "Бригада 2", ROUTER, 2)


def test_transfer_lets_the_receiver_take_the_order():
    """Смысл передачи: после неё бригада может взять заявку."""
    from dispatcher.services.equipment import transfer

    plan, orders = bag_day()
    issued = issued_items(plan, orders)
    extra = bag_order("9", [ROUTER])
    assert missing_for(extra, "Бригада 2", issued, plan, orders) == [ROUTER]

    updated = transfer(issued, plan, orders, "Бригада 1", "Бригада 2", ROUTER, 1)

    assert missing_for(extra, "Бригада 2", updated, plan, orders) == []


def test_transfer_refuses_nonsense():
    from dispatcher.services.equipment import transfer

    plan, orders = bag_day()
    issued = issued_items(plan, orders)
    with pytest.raises(ValueError):
        transfer(issued, plan, orders, "Бригада 1", "Бригада 1", ROUTER, 1)
    with pytest.raises(ValueError):
        transfer(issued, plan, orders, "Бригада 1", "Бригада 2", "Дрель", 1)


def test_full_rebuild_respects_bags_and_pins(scenarios):
    """Пересборка дня: не больше устройств, чем выдано, и закреплённое на месте.

    Раньше решатель при пересборке ничего не знал о сумке и закреплениях:
    бригада получала шесть роутеров при трёх выданных, а закреплённая
    диспетчером заявка уезжала к другой бригаде.
    """
    from dispatcher.services.equipment import planned_items
    from dispatcher.services.planning.baseline import solve_greedy
    from dispatcher.services.replanning.apply import replan
    from dispatcher.services.replanning.events import KIND_UNAVAILABLE, ReplanEvent

    scenario = scenarios["vostok"]
    plan = solve_greedy(scenario.orders, scenario.engineers)
    issued = issued_items(plan, scenario.orders)
    busy = [r for r in plan.routes if len(r.stops) >= 2]
    gone, keeper = busy[0].engineer_id, busy[1].engineer_id
    pinned_order = busy[1].stops[-1].order_id
    event = ReplanEvent(kind=KIND_UNAVAILABLE, at=11 * 60, engineer_id=gone)

    result = replan(scenario.orders, scenario.engineers, plan, event, mode="full",
                    time_limit_sec=4, issued=issued, locked={pinned_order: keeper})

    for route in result.plan.routes:
        carried = issued.get(route.engineer_id, {})
        for item, count in planned_items(result.plan, result.orders,
                                         route.engineer_id).items():
            assert count <= carried.get(item, 0), (route.engineer_id, item, count)
    holder = {s.order_id: r.engineer_id for r in result.plan.routes for s in r.stops}
    assert holder.get(pinned_order) == keeper
