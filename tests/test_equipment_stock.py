"""Остаток оборудования: что бригада может взять днём.

Ответ организаторов: бригада получает оборудование в офисе сразу на весь
день, и при перепланировании ей можно назначать только те заявки, под
которые оборудование у неё есть.
"""
from dispatcher.domain import Order, Plan, Route, Stop
from dispatcher.domain.catalog import VEHICLE_CAR
from dispatcher.domain.equipment import ROUTER, SPARE_PER_ITEM, TV_BOX
from dispatcher.services.equipment import Stock, issued_items, missing_for

SKILL = "Работы на подключение"


def _order(order_id: str, equipment: list[str]) -> Order:
    return Order(id=order_id, lat=55.7, lon=37.6, address="", district="",
                 duration_min=30, window_start=600, window_end=720,
                 priority="Обычная", required_skill="Работы на подключение",
                 equipment=equipment)


def _stop(order_id: str) -> Stop:
    return Stop(order_id=order_id, arrival=600, start=600, end=630,
                travel_min=10, travel_km=2.0, wait_min=0)


def _day():
    """Бригада 1 везёт два роутера, бригада 2 не везёт ничего."""
    orders = [_order("1", [ROUTER]), _order("2", [ROUTER]), _order("3", [])]
    plan = Plan(routes=[
        Route(engineer_id="Бригада 1", stops=[_stop("1"), _stop("2")]),
        Route(engineer_id="Бригада 2", stops=[_stop("3")]),
    ])
    return plan, orders


def test_issue_adds_a_spare_to_those_who_carry():
    plan, orders = _day()

    issued = issued_items(plan, orders)

    assert issued["Бригада 1"][ROUTER] == 2 + SPARE_PER_ITEM
    assert issued["Бригада 1"][TV_BOX] == SPARE_PER_ITEM
    # Бригада без оборудования в офис не заходит и запаса не получает.
    assert "Бригада 2" not in issued


def test_spare_lets_one_more_order_in():
    plan, orders = _day()
    issued = issued_items(plan, orders)

    assert missing_for(_order("4", [ROUTER]), "Бригада 1", issued, plan, orders) == []


def test_third_router_does_not_fit():
    """Запас один: вторую лишнюю заявку той же бригаде уже не отдать."""
    plan, orders = _day()
    issued = issued_items(plan, orders)
    stock = Stock(issued)
    stock.fill({"Бригада 1": [orders[0], orders[1]]})

    extra = _order("4", [ROUTER])
    assert stock.can_take("Бригада 1", extra) is True
    stock.take("Бригада 1", extra)
    assert stock.can_take("Бригада 1", _order("5", [ROUTER])) is False


def test_crew_without_equipment_takes_nothing():
    plan, orders = _day()
    issued = issued_items(plan, orders)

    short = missing_for(_order("4", [ROUTER]), "Бригада 2", issued, plan, orders)
    assert short == [ROUTER]


def test_order_without_equipment_is_always_allowed():
    plan, orders = _day()
    issued = issued_items(plan, orders)

    assert missing_for(_order("4", []), "Бригада 2", issued, plan, orders) == []


def test_before_the_morning_issue_there_is_no_limit():
    """День ещё не построен - ограничивать нечем, набор соберётся по плану."""
    plan, orders = _day()

    assert missing_for(_order("4", [ROUTER]), "Бригада 2", {}, plan, orders) == []
    assert Stock({}).enforced is False


def test_released_order_frees_the_bag():
    plan, orders = _day()
    stock = Stock(issued_items(plan, orders))
    stock.fill({"Бригада 1": [orders[0], orders[1]]})
    stock.take("Бригада 1", _order("4", [ROUTER]))

    assert stock.can_take("Бригада 1", _order("5", [ROUTER])) is False
    stock.release("Бригада 1", orders[0])
    assert stock.can_take("Бригада 1", _order("5", [ROUTER])) is True


def test_replan_passes_the_order_by_the_empty_bag():
    """Сквозная проверка на дне, собранном под сам этот выбор.

    Ближняя бригада едет без оборудования, дальняя везёт роутеры. Срочная
    заявка с роутером приходит к порогу ближней: без учёта сумки её взяла бы
    она, с учётом - заявка уезжает к дальней. На боевых данных такой тест
    ничего не показывает: там узкое место не оборудование, и обе версии
    кода дают одно и то же назначение.
    """
    from dispatcher.domain import PRIORITY_URGENT, Engineer
    from dispatcher.services.replanning.apply import replan
    from dispatcher.services.replanning.events import KIND_URGENT, ReplanEvent

    near = Engineer(id="near", name="Ближняя", lat=55.70, lon=37.60,
                    start_address="", shift_start=540, shift_end=1140,
                    skills=[SKILL], vehicle=VEHICLE_CAR)
    far = Engineer(id="far", name="Дальняя", lat=55.78, lon=37.72,
                   start_address="", shift_start=540, shift_end=1140,
                   skills=[SKILL], vehicle=VEHICLE_CAR)
    engineers = [near, far]

    # Утро: ближняя работает без оборудования, дальняя везёт роутер.
    orders = [_at("near-1", 55.70, 37.60, []), _at("far-1", 55.78, 37.72, [ROUTER])]
    plan = Plan(routes=[Route(engineer_id="near", stops=[_stop("near-1")]),
                        Route(engineer_id="far", stops=[_stop("far-1")])])
    issued = issued_items(plan, orders)
    assert ROUTER not in issued.get("near", {})

    urgent = _at("urgent-1", 55.701, 37.601, [ROUTER], priority=PRIORITY_URGENT,
                 window=(13 * 60, 18 * 60))
    event = ReplanEvent(kind=KIND_URGENT, at=13 * 60, new_order=urgent)

    free = replan(orders, engineers, plan, event, time_limit_sec=4)
    limited = replan(orders, engineers, plan, event, time_limit_sec=4,
                     issued=issued)

    assert _holder(free.plan, "urgent-1") == "near", (
        "без ограничения заявку должна взять ближняя - иначе тест ничего "
        "не проверяет")
    assert _holder(limited.plan, "urgent-1") == "far"


def _holder(plan: Plan, order_id: str) -> str | None:
    """Кто везёт эту заявку."""
    return next((route.engineer_id for route in plan.routes
                 if any(stop.order_id == order_id for stop in route.stops)), None)


def _at(order_id: str, lat: float, lon: float, equipment: list[str],
        priority: str = "Обычная",
        window: tuple[int, int] = (600, 1080)) -> Order:
    """Заявка в заданной точке."""
    return Order(id=order_id, lat=lat, lon=lon, address="", district="",
                 duration_min=30, window_start=window[0], window_end=window[1],
                 priority=priority, required_skill=SKILL, equipment=equipment)


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

    plan, orders = _day()
    rows = issued_rows(issued_items(plan, orders))

    assert len(rows) == 1
    row = rows[0]
    assert row["engineer_id"] == "Бригада 1"
    assert row["items"][ROUTER] == 2 + SPARE_PER_ITEM
    assert row["total"] == sum(row["items"].values())
