"""Сохранённый день поднимается таким же, каким был.

Файл сохранения и журнал в базе складывают день одним снимком. Раньше в
снимок не попадали отметки хода работ, выданное оборудование и правило
выезда после события: после «Восстановить» отметки пропадали, ограничение
по сумке выключалось, а время визитов молча становилось другим - бригада
«приезжала» на аварию в момент её поступления.
"""
from dispatcher.domain import PRIORITY_URGENT, SKILL_LOCAL, STATUS_DONE, Engineer, Order, Plan
from dispatcher.domain.catalog import VEHICLE_CAR
from dispatcher.services.dataset import (
    rebuild,
    snapshot_from_json,
    snapshot_of,
    snapshot_to_json,
)
from dispatcher.services.replanning.apply import replan
from dispatcher.services.replanning.events import KIND_URGENT, ReplanEvent
from dispatcher.services.routing import evaluate_sequence

LAT, LON = 55.75, 37.62


def _order(order_id: str, start: int, north: float = 0.0,
           priority: str = "Обычная") -> Order:
    return Order(id=order_id, lat=LAT + north, lon=LON, address="", district="",
                 duration_min=60, window_start=start, window_end=start + 300,
                 priority=priority, required_skill=SKILL_LOCAL)


def test_day_after_an_event_comes_back_unchanged():
    crew = Engineer(id="crew", name="Бригада", lat=LAT, lon=LON, start_address="",
                    shift_start=9 * 60, shift_end=19 * 60, skills=[SKILL_LOCAL],
                    vehicle=VEHICLE_CAR)
    orders = [_order("a", 9 * 60), _order("b", 12 * 60, 0.02)]
    route, _ = evaluate_sequence(crew, orders)
    assert route is not None
    emergency = _order("sos", 11 * 60, 0.03, PRIORITY_URGENT)
    result = replan(orders, [crew], Plan(routes=[route]),
                    ReplanEvent(kind=KIND_URGENT, at=11 * 60, new_order=emergency),
                    time_limit_sec=4)
    issued = {"crew": {"Роутер": 2}}
    statuses = {"a": STATUS_DONE}

    data = snapshot_to_json(snapshot_of(
        "r", "Участок", "Событие", result.plan, result.orders, result.engineers,
        {}, True, issued=issued, statuses=statuses))
    back = snapshot_from_json(data)
    plan, _, _ = rebuild(back)

    before = {s.order_id: (s.arrival, s.start) for r in result.plan.routes for s in r.stops}
    after = {s.order_id: (s.arrival, s.start) for r in plan.routes for s in r.stops}
    assert after == before
    assert back.issued == issued
    assert back.statuses == statuses
    assert back.engineers[0].resume_at == 11 * 60


def test_save_and_restore_keep_marks_and_equipment(tmp_path, monkeypatch):
    """Ручки «Сохранить день» и «Восстановить» не теряют отметки и сумки."""
    from fastapi.testclient import TestClient

    from dispatcher.api import deps
    from dispatcher.api.app import app
    from dispatcher.api.routes import saving

    deps.JOURNAL.available = False
    monkeypatch.setattr(saving, "SAVED_DIR", str(tmp_path))
    region = "yugocentr"
    with TestClient(app) as client:
        plan = client.post("/api/plan", json={"region": region, "strategy": "greedy"})
        first = next(r for r in plan.json()["data"]["routes"] if r["stops"])
        order_id = first["stops"][0]["order_id"]
        client.post("/api/order/status",
                    json={"region": region, "order_id": order_id, "status": STATUS_DONE})
        issued = deps.STORE.current(region).issued

        client.post("/api/plan/save", json={"region": region, "name": "тест"})
        client.post("/api/plan", json={"region": region, "strategy": "greedy",
                                       "reset": True})
        restored = client.post("/api/plan/restore", json={"region": region})

        assert restored.json()["data"]["statuses"].get(order_id) == STATUS_DONE
        assert deps.STORE.current(region).issued == issued
