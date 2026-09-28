"""Бригада, не вышедшая на смену, работу по событию не получает.

Организаторы (22.09, 24.09): бригада, которой утренний план не дал заявок,
в этот день не выходит. Новая заявка или авария днём не вызывает её из
дома; это форс-мажор, и решает его диспетчер вручную.

День собран под сам выбор: у работающей бригады визиты плотные, а вторая
свободна весь день. Без правила новая заявка уходит второй бригаде.
"""
import pytest
from day_fixtures import EVENT_AT, LAT, LON, one_crew_day, order_at
from fastapi.testclient import TestClient

from dispatcher.domain import (
    PRIORITY_NORMAL,
    PRIORITY_URGENT,
    SKILL_LOCAL,
    Engineer,
    Plan,
    Route,
)
from dispatcher.domain.catalog import VEHICLE_CAR
from dispatcher.services.dataset import snapshot_from_json, snapshot_of, snapshot_to_json
from dispatcher.services.replanning.apply import replan
from dispatcher.services.replanning.events import KIND_URGENT, ReplanEvent
from dispatcher.services.roster import roster_of


def _day_with_crew_at_home():
    engineers, orders, plan = one_crew_day()
    home = Engineer(id="home", name="Бригада дома", lat=LAT, lon=LON, start_address="",
                    shift_start=9 * 60, shift_end=17 * 60, skills=[SKILL_LOCAL],
                    vehicle=VEHICLE_CAR)
    plan = Plan(routes=[*plan.routes, Route(engineer_id="home")])
    return [*engineers, home], orders, plan


def _placed_at(plan: Plan, order_id: str) -> str | None:
    return next((r.engineer_id for r in plan.routes
                 if any(s.order_id == order_id for s in r.stops)), None)


def _replan(priority: str, on_shift: list[str] | None, mode: str = "minimal",
            duration: int = 60):
    engineers, orders, plan = _day_with_crew_at_home()
    new = order_at("new", 12 * 60, duration, priority, window=240)
    event = ReplanEvent(kind=KIND_URGENT, at=EVENT_AT, new_order=new)
    return replan(orders, engineers, plan, event, mode=mode, time_limit_sec=4,
                  on_shift=on_shift)


def test_without_a_roster_the_crew_at_home_takes_the_order():
    """Контроль: без состава смены заявку берёт бригада из дома."""
    assert _placed_at(_replan(PRIORITY_NORMAL, None).plan, "new") == "home"


def test_ordinary_order_does_not_call_a_crew_from_home():
    result = _replan(PRIORITY_NORMAL, ["crew"])

    assert _placed_at(result.plan, "new") is None
    reason = next(u for u in result.plan.unassigned if u.order_id == "new")
    assert "не на смене: Бригада дома" in reason.reason_text
    assert any(r.engineer_id == "home" and not r.stops for r in result.plan.routes)


def test_emergency_rebuild_does_not_call_a_crew_from_home():
    """Пересборка остатка дня ради аварии тоже раздаёт работу только вышедшим.

    Трёхчасовая авария вытесняет два визита работающей бригады; без состава
    смены их забирает бригада из дома - контроль это показывает.
    """
    free = _replan(PRIORITY_URGENT, None, "full", 180).plan
    assert next(r for r in free.routes if r.engineer_id == "home").stops
    result = _replan(PRIORITY_URGENT, ["crew"], mode="full", duration=180)

    home = next(r for r in result.plan.routes if r.engineer_id == "home")
    assert not home.stops
    assert _placed_at(result.plan, "new") in (None, "crew")


def test_roster_survives_the_snapshot():
    engineers, orders, plan = _day_with_crew_at_home()
    data = snapshot_to_json(snapshot_of("r", "Участок", "План", plan, orders, engineers,
                                        {}, False, on_shift=["crew"]))
    assert snapshot_from_json(data).on_shift == ["crew"]
    del data["on_shift"]
    assert snapshot_from_json(data).on_shift is None


@pytest.fixture(scope="module")
def client():
    from dispatcher.api import deps
    from dispatcher.api.app import app

    deps.JOURNAL.available = False
    with TestClient(app) as test_client:
        yield test_client


def test_morning_plan_sets_the_roster(client):
    region = "vostok"
    assert client.post("/api/plan", json={"region": region, "strategy": "greedy",
                                          "reset": True}).status_code == 200
    from dispatcher.api.deps import STORE
    state = STORE.current(region)
    assert state is not None and state.on_shift is not None
    used = {r.engineer_id for r in state.plan.routes if r.stops}
    assert set(state.on_shift) == used


def test_manual_call_joins_the_roster():
    """Ручное назначение и есть вызов с выходного: бригада выходит на смену."""
    engineers, orders, plan = _day_with_crew_at_home()
    first = plan.routes[0]
    called = Plan(routes=[first, Route(engineer_id="home", stops=first.stops[:1])])
    assert roster_of(called, ["crew"]) == ["crew", "home"]
    assert roster_of(plan, []) == ["crew"]
