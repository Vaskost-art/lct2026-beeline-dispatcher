"""Правка не ложится поверх изменившегося дня.

Расчёт длится до минуты. Раньше правка, пришедшая за это время, молча
терялась, а предпросмотр события привязывался к числу версий - после шага
назад и новой правки оно то же, и событие применялось к чужому дню, откатывая
последнее решение диспетчера.
"""
import pytest

from dispatcher.api.envelope import ApiError
from dispatcher.domain import STATUS_CANCELLED, STATUS_DONE


def test_stale_write_is_refused(scenarios):
    from dispatcher.api.state import DayStore, DayVersion
    from dispatcher.domain import Plan

    key, scenario = next(iter(scenarios.items()))
    store = DayStore({key: scenario})

    def version(label: str) -> DayVersion:
        return DayVersion(label=label, plan=Plan(routes=[]), metrics={},
                          orders=list(scenario.orders), engineers=list(scenario.engineers))

    started = store.revision(key)
    store.push(key, version("чужая правка"))
    with pytest.raises(ApiError) as refused:
        store.push_since(started, key, version("долгий расчёт"))
    assert refused.value.status_code == 409
    assert store.current(key).label == "чужая правка"


def test_preview_is_not_applied_to_a_changed_day():
    """Правка, предпросмотр, шаг назад, другая правка - применяется свежий расчёт."""
    from fastapi.testclient import TestClient

    from dispatcher.api import deps
    from dispatcher.api.app import app

    deps.JOURNAL.available = False
    region = "yugocentr"
    with TestClient(app) as client:
        plan = client.post("/api/plan", json={"region": region, "strategy": "greedy"})
        routes = [r for r in plan.json()["data"]["routes"] if len(r["stops"]) >= 2]
        first, second = routes[0]["stops"][0]["order_id"], routes[1]["stops"][0]["order_id"]
        cancel = routes[1]["stops"][-1]["order_id"]
        event = {"region": region, "kind": "cancel_order", "order_id": cancel,
                 "at": "08:00", "mode": "minimal"}

        # Правка A: заявка отменена, из предпросмотра она исключена.
        client.post("/api/order/status",
                    json={"region": region, "order_id": first, "status": STATUS_CANCELLED})
        client.post("/api/replan", json={**event, "apply": False})
        # Шаг назад отменяет A, правка B - отметка у другой заявки.
        client.post("/api/undo", json={"region": region})
        client.post("/api/order/status",
                    json={"region": region, "order_id": second, "status": STATUS_DONE})
        applied = client.post("/api/replan", json={**event, "apply": True})

        placed = {stop["order_id"] for route in applied.json()["data"]["routes"]
                  for stop in route["stops"]}
        assert first in placed, "применился предпросмотр, посчитанный до шага назад"
