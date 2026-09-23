"""Новая заявка в пределах возможного: тесный день, конец смены, чужие отказы.

Продолжение `test_new_order_event.py`: те же правила организаторов (22.09),
проверенные на краях - когда места нет, смена кончилась или событие не
касается утренних отказов.
"""
from day_fixtures import (
    LAT,
    LON,
    one_crew_day,
    order_at,
    starts,
)

from dispatcher.domain import (
    PRIORITY_HIGH,
    PRIORITY_NORMAL,
    PRIORITY_URGENT,
    SKILL_LOCAL,
    Engineer,
    Order,
)
from dispatcher.domain.catalog import VEHICLE_CAR
from dispatcher.services.replanning.apply import replan
from dispatcher.services.replanning.events import KIND_URGENT, ReplanEvent
from dispatcher.services.routing import evaluate_sequence


def _tight_day():
    """Жёсткие окна: визит нельзя сдвинуть ни на минуту; смена до 19:00.

    Авария, пришедшая в 11:30, без снятия заявки встаёт только в конец
    дня - через пять часов. Уложиться в два часа можно, лишь освободив
    место: ориентир организаторов для реакции на аварию - 1-2 часа.
    """
    from dispatcher.domain import Plan

    crew = Engineer(id="crew", name="Бригада", lat=LAT, lon=LON, start_address="",
                    shift_start=9 * 60, shift_end=19 * 60, skills=[SKILL_LOCAL],
                    vehicle=VEHICLE_CAR)
    orders = [order_at(f"o{hour}", hour * 60, 90, window=0) for hour in (9, 11, 13, 15)]
    route, _ = evaluate_sequence(crew, orders)
    assert route is not None
    return [crew], orders, Plan(routes=[route])


def test_emergency_takes_the_place_of_an_ordinary_order_to_arrive_in_time():
    """Авария важнее ремонта: ради приезда в срок ремонт уступает место."""
    at = 11 * 60 + 30
    emergency = order_at("new", at, 80, PRIORITY_URGENT, window=12 * 60)
    for mode in ("minimal", "full"):
        engineers, orders, plan = _tight_day()
        event = ReplanEvent(kind=KIND_URGENT, at=at, new_order=emergency)
        result = replan(orders, engineers, plan, event, mode=mode, time_limit_sec=4)

        info = result.diff.get("reaction")
        assert info is not None and info["minutes"] <= 120, (mode, info)
        gave_way = [u for u in result.plan.unassigned if u.order_id != "new"]
        assert len(gave_way) == 1, (mode, [u.order_id for u in gave_way])
        assert "авари" in gave_way[0].reason_text.lower(), (mode, gave_way[0].reason_text)


def test_full_rebuild_survives_a_crew_whose_shift_is_over():
    """Смена бригады A кончилась до события - пересборка дня не пустеет.

    Правило «к новому заданию не раньше события» ставилось и на пустой
    маршрут, и для бригады со смены до 13:00 при событии в 14:00 модель
    становилась неразрешимой: пересборка отдавала 0 назначенных заявок.
    """
    from dispatcher.domain import Plan
    from dispatcher.services.replanning.events import KIND_CANCEL

    def at(order_id: str, start: int, north: float = 0.0) -> Order:
        return Order(id=order_id, lat=LAT + north, lon=LON, address="", district="",
                     duration_min=60, window_start=start, window_end=start + 240,
                     priority=PRIORITY_NORMAL, required_skill=SKILL_LOCAL)

    short = Engineer(id="A", name="A", lat=LAT, lon=LON, start_address="",
                     shift_start=8 * 60, shift_end=13 * 60, skills=[SKILL_LOCAL],
                     vehicle=VEHICLE_CAR)
    long = Engineer(id="B", name="B", lat=LAT, lon=LON, start_address="",
                    shift_start=9 * 60, shift_end=19 * 60, skills=[SKILL_LOCAL],
                    vehicle=VEHICLE_CAR)
    orders = [at("a1", 8 * 60), at("a2", 10 * 60), at("b1", 9 * 60),
              at("b2", 15 * 60, 0.01), at("b3", 16 * 60, 0.02)]
    first, _ = evaluate_sequence(short, orders[:2])
    second, _ = evaluate_sequence(long, orders[2:])
    assert first is not None and second is not None
    plan = Plan(routes=[first, second])

    event = ReplanEvent(kind=KIND_CANCEL, at=14 * 60, order_id="b3")
    result = replan(orders, [short, long], plan, event, mode="full", time_limit_sec=4)

    placed = {stop.order_id for route in result.plan.routes for stop in route.stops}
    assert {"a1", "a2", "b1", "b2"} <= placed, result.plan.solver_status


def _real_day(scenarios, key: str):
    from dispatcher.services.planning.baseline import solve_greedy

    scenario = scenarios[key]
    return scenario, solve_greedy(scenario.orders, scenario.engineers)


def test_ordinary_order_leaves_morning_refusals_alone():
    """Обычная заявка не повод заново расставлять утренние отказы.

    Утренняя заявка без исполнителя встаёт только ценой сдвига соседних
    визитов. Раньше она расставлялась заново вместе с новой обычной заявкой,
    и соседи сдвигались - а обычной заявке это запрещено.
    """
    engineers, orders, plan = one_crew_day()
    left = order_at("left", 12 * 60, 60, PRIORITY_NORMAL, window=240)
    new = order_at("new", 12 * 60, 20, PRIORITY_HIGH, window=240)
    event = ReplanEvent(kind=KIND_URGENT, at=12 * 60, new_order=new)
    result = replan([*orders, left], engineers, plan, event, time_limit_sec=4)

    old = {"o13", "o15"}
    assert starts(result.plan, old) == starts(plan, old)
    assert "left" in {u.order_id for u in result.plan.unassigned}


def test_other_events_do_not_blame_an_emergency(scenarios):
    """Бригада выбыла, аварии днём не было - «уступила место аварии» не пишем."""
    from dispatcher.services.replanning.events import KIND_UNAVAILABLE

    scenario, plan = _real_day(scenarios, "vostok")
    crew = next(r.engineer_id for r in plan.routes if r.stops)
    event = ReplanEvent(kind=KIND_UNAVAILABLE, at=9 * 60, engineer_id=crew)
    result = replan(scenario.orders, scenario.engineers, plan, event,
                    mode="full", time_limit_sec=4)

    assert not [u for u in result.plan.unassigned if "аварии" in u.reason_text]


def test_daytime_emergency_needs_a_car_like_morning_one():
    """Авария днём требует машину по тому же правилу, что и утренняя."""
    from dispatcher.domain.catalog import SKILL_EMERGENCY
    from dispatcher.services.replanning.events import make_new_order

    emergency = make_new_order("a", LAT, LON, "", "", 60, 12 * 60, 23 * 60,
                               SKILL_EMERGENCY)
    ordinary = make_new_order("o", LAT, LON, "", "", 60, 12 * 60, 14 * 60, SKILL_LOCAL)

    assert emergency.required_vehicle == VEHICLE_CAR
    assert ordinary.required_vehicle is None


def test_every_region_can_take_a_daytime_emergency(scenarios):
    """На каждом участке хотя бы одна бригада с допуском к авариям на машине.

    На Югоцентре машины доставались бригадам под гигабитные подключения, и
    авария, пришедшая днём (а она требует машину), не вставала ни к кому.
    """
    from dispatcher.domain.catalog import SKILL_EMERGENCY

    for key, scenario in scenarios.items():
        rescuers = [crew for crew in scenario.engineers if SKILL_EMERGENCY in crew.skills]
        assert any(crew.vehicle == VEHICLE_CAR for crew in rescuers), key


def test_only_the_rescue_crew_orders_gave_way():
    """«Уступила место аварии» - только у заявки бригады, что поехала на аварию."""
    from dispatcher.domain import Plan, Route, Stop, Unassigned
    from dispatcher.services.replanning.emergency import credit_gave_way

    def stop(order_id: str) -> Stop:
        return Stop(order_id=order_id, arrival=600, start=600, end=630,
                    travel_min=5, travel_km=1.0, wait_min=0)

    before = Plan(routes=[Route(engineer_id="A", stops=[stop("mine")]),
                          Route(engineer_id="B", stops=[stop("other")])])
    after = Plan(routes=[Route(engineer_id="A", stops=[stop("crash")]),
                         Route(engineer_id="B", stops=[])],
                 unassigned=[Unassigned("mine", "no_capacity", "занято"),
                             Unassigned("other", "no_capacity", "занято")])

    credit_gave_way(before, after, {"crash": 700})

    reasons = {item.order_id: item.reason for item in after.unassigned}
    assert reasons == {"mine": "displaced_by_urgent", "other": "no_capacity"}
