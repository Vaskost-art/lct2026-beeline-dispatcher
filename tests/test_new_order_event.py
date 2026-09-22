"""Новая заявка в течение дня: авария и всё остальное ведут себя по-разному.

Организаторы (22.09): новая обычная заявка, если помещается в свободный
интервал инженера между уже запланированными работами, может быть
добавлена, но не должна перестраивать сформированный план. Авария может
перепланировать остаток дня.

День собран под сам этот выбор: одна бригада, визиты плотно, промежутки по
полчаса. Часовая заявка влезает только ценой сдвига чужих визитов - это
разрешено аварии и запрещено обычной. На боевых данных такой тест ничего бы
не показал: там у кого-нибудь почти всегда есть свободный вечер.
"""
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

LAT, LON = 55.75, 37.62
EVENT_AT = 12 * 60


def _order(order_id: str, start: int, duration: int, priority: str = PRIORITY_NORMAL,
           window: int = 60) -> Order:
    return Order(id=order_id, lat=LAT, lon=LON, address="", district="",
                 duration_min=duration, window_start=start, window_end=start + window,
                 priority=priority, required_skill=SKILL_LOCAL)


def _day():
    """Визиты 9:00, 11:00, 13:00, 15:00 по полтора часа; смена до 17:00."""
    crew = Engineer(id="crew", name="Бригада", lat=LAT, lon=LON, start_address="",
                    shift_start=9 * 60, shift_end=17 * 60, skills=[SKILL_LOCAL],
                    vehicle=VEHICLE_CAR)
    orders = [_order(f"o{hour}", hour * 60, 90) for hour in (9, 11, 13, 15)]
    route, _ = evaluate_sequence(crew, orders)
    assert route is not None
    from dispatcher.domain import Plan
    return [crew], orders, Plan(routes=[route])


def _starts(plan, ids):
    return {stop.order_id: stop.start for route in plan.routes
            for stop in route.stops if stop.order_id in ids}


def _replan(new: Order, mode: str = "minimal"):
    engineers, orders, plan = _day()
    event = ReplanEvent(kind=KIND_URGENT, at=EVENT_AT, new_order=new)
    result = replan(orders, engineers, plan, event, mode=mode, time_limit_sec=4)
    return plan, result


def test_ordinary_order_does_not_push_other_visits():
    """Часовой ремонт влез бы только сдвигом соседей - значит, не встаёт."""
    before, result = _replan(_order("new", 12 * 60, 60, PRIORITY_NORMAL, window=240))

    placed = {s.order_id for r in result.plan.routes for s in r.stops}
    assert "new" not in placed
    old = {"o9", "o11", "o13", "o15"}
    assert _starts(result.plan, old) == _starts(before, old)
    reason = next(u for u in result.plan.unassigned if u.order_id == "new")
    assert "свободн" in reason.reason_text


def test_emergency_may_reshape_the_rest_of_the_day():
    """Та же заявка, но авария: встаёт, соседи сдвигаются."""
    before, result = _replan(_order("new", 12 * 60, 60, PRIORITY_URGENT, window=240))

    placed = {s.order_id for r in result.plan.routes for s in r.stops}
    assert "new" in placed
    old = {"o13", "o15"}
    assert _starts(result.plan, old) != _starts(before, old)


def test_short_ordinary_order_fits_a_free_gap():
    """Двадцать минут помещаются в получасовой промежуток, никого не двигая."""
    before, result = _replan(_order("new", 12 * 60, 20, PRIORITY_HIGH, window=240))

    placed = {s.order_id for r in result.plan.routes for s in r.stops}
    assert "new" in placed
    old = {"o13", "o15"}
    assert _starts(result.plan, old) == _starts(before, old)


def test_full_mode_does_not_rebuild_the_day_for_an_ordinary_order():
    """Пересборка остатка дня - право аварии, обычной заявке её не дают."""
    before, result = _replan(_order("new", 12 * 60, 60, PRIORITY_NORMAL, window=240),
                             mode="full")

    old = {"o13", "o15"}
    assert _starts(result.plan, old) == _starts(before, old)
    assert result.diff.get("mode") == "minimal"


def test_emergency_reports_reaction_time():
    """Время реакции считается от поступления до прибытия бригады."""
    _, result = _replan(_order("new", 12 * 60, 60, PRIORITY_URGENT, window=240))

    info = result.diff["reaction"]
    stop = next(s for r in result.plan.routes for s in r.stops if s.order_id == "new")
    assert info["minutes"] == stop.arrival - EVENT_AT
    assert info["within"] is (info["minutes"] <= 120)
    assert any("прибудет на аварию" in line for line in result.narrative)


def test_ordinary_order_has_no_reaction_target():
    """Ориентир 1-2 часа - про аварию; у обычной заявки его нет."""
    _, result = _replan(_order("new", 12 * 60, 20, PRIORITY_HIGH, window=240))

    assert "reaction" not in result.diff


def test_new_order_priority_follows_the_work_type():
    """Днём приходят не только аварии: приоритет берётся из типа работ."""
    from dispatcher.domain import SKILL_CONNECT, SKILL_EMERGENCY
    from dispatcher.services.replanning.events import make_new_order

    def made(skill: str) -> str:
        return make_new_order("x", LAT, LON, "", "", 30, 600, 700, skill).priority

    assert made(SKILL_EMERGENCY) == PRIORITY_URGENT
    assert made(SKILL_CONNECT) == PRIORITY_HIGH
    assert made(SKILL_LOCAL) == PRIORITY_NORMAL


def test_crew_cannot_leave_for_an_emergency_before_it_arrives():
    """Бригада свободна с 10:30, авария поступает в 10:40 в трёх километрах.

    Раньше план выпускал бригаду в 10:30 и доставлял её к аварии до того,
    как та поступила: время реакции выходило отрицательным.
    """
    from dispatcher.domain.distance import road_km, travel_minutes

    engineers, orders, plan = _day()
    far = Order(id="new", lat=LAT + 0.027, lon=LON, address="", district="",
                duration_min=30, window_start=10 * 60 + 40, window_end=16 * 60,
                priority=PRIORITY_URGENT, required_skill=SKILL_LOCAL)
    at = 10 * 60 + 40
    for mode in ("minimal", "full"):
        event = ReplanEvent(kind=KIND_URGENT, at=at, new_order=far)
        result = replan(orders, engineers, plan, event, mode=mode, time_limit_sec=4)
        info = result.diff.get("reaction")
        assert info is not None, mode
        drive = travel_minutes(road_km(LAT, LON, far.lat, far.lon), VEHICLE_CAR)
        assert info["minutes"] >= drive, (mode, info["minutes"], drive)


def test_inserted_order_does_not_mark_neighbours_as_reordered():
    """Номера после вставки сдвигаются, но порядок соседей тот же.

    Раньше список изменений помечал все следующие визиты «сменила место в
    маршруте», хотя ни порядок, ни время у них не менялись.
    """
    _, result = _replan(_order("new", 12 * 60, 20, PRIORITY_HIGH, window=240))

    statuses = {c["order_id"]: c["status"] for c in result.diff["changes"]}
    assert statuses.get("new") == "added"
    assert not {oid for oid, status in statuses.items()
                if status in ("resequenced", "retimed")}


def test_emergency_shows_whose_visit_moved_in_time():
    """Авария сдвинула соседей - диспетчер видит, кому звонить."""
    _, result = _replan(_order("new", 12 * 60, 60, PRIORITY_URGENT, window=240))

    retimed = [c for c in result.diff["changes"] if c["status"] == "retimed"]
    assert retimed
    assert all(c["shift_min"] > 0 for c in retimed)


def test_event_does_not_delay_a_crew_already_on_its_way():
    """Бригада выехала к своей заявке до события - её визит не сдвигается.

    Правило «к новому заданию не раньше события» сначала применялось ко
    всем заявкам, и любое событие задерживало все бригады на время дороги:
    в предпросмотре появлялись визиты «сдвинут позже на 30 мин» у тех, кого
    событие не касалось.
    """
    from dispatcher.domain import Plan
    from dispatcher.services.replanning.events import KIND_CANCEL

    crew = Engineer(id="crew", name="Бригада", lat=LAT, lon=LON, start_address="",
                    shift_start=9 * 60, shift_end=18 * 60, skills=[SKILL_LOCAL],
                    vehicle=VEHICLE_CAR)
    near = _order("near", 11 * 60, 90)                      # 11:00-12:30
    far = Order(id="far", lat=LAT + 0.05, lon=LON, address="", district="",
                duration_min=60, window_start=12 * 60 + 30, window_end=15 * 60,
                priority=PRIORITY_NORMAL, required_skill=SKILL_LOCAL)
    last = _order("last", 16 * 60, 30)
    orders = [near, far, last]
    route, _ = evaluate_sequence(crew, orders)
    assert route is not None
    plan = Plan(routes=[route])
    before = _starts(plan, {"far"})
    departed = route.stops[1].arrival - route.stops[1].travel_min
    at = departed + 5                                    # бригада уже в пути

    event = ReplanEvent(kind=KIND_CANCEL, at=at, order_id="last")
    for mode in ("minimal", "full"):
        result = replan(orders, [crew], plan, event, mode=mode, time_limit_sec=4)
        assert _starts(result.plan, {"far"}) == before, mode
