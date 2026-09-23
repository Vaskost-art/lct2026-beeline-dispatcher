"""Согласованность дня между действиями диспетчера, второй круг ревью.

Каждый случай воспроизведён ревьюерами на живом сервисе: отменённая заявка
исчезала после следующего события, и её номер снова выдавался новой аварии;
событие во времени раньше прошлого снимало заморозку с начатых работ;
«Применить» молча пересчитывало событие по изменившемуся дню; «Шаг назад»
подписывал себя чужим действием.
"""
import warnings

import pytest
from fastapi.testclient import TestClient

warnings.filterwarnings("ignore")

REGION = "yugocentr"


@pytest.fixture()
def client():
    from dispatcher.api import deps
    from dispatcher.api.app import app

    deps.JOURNAL.available = False
    with TestClient(app) as test_client:
        answer = test_client.post("/api/plan", json={"region": REGION, "strategy": "greedy",
                                                     "reset": True})
        assert answer.status_code == 200
        yield test_client


def _first_assigned(client) -> str:
    plan = client.get(f"/api/plan/{REGION}").json()["data"]
    return plan["routes"][0]["stops"][-1]["order_id"]


def _delay(at: str, apply: bool) -> dict:
    return {"region": REGION, "kind": "engineer_delayed", "at": at,
            "engineer_id": "Бригада 1", "delay_min": 15, "mode": "minimal",
            "apply": apply, "time_limit_sec": 5}


def test_cancelled_order_survives_the_next_event_and_keeps_its_number(client):
    order_id = _first_assigned(client)
    assert client.post("/api/order/status", json={"region": REGION, "order_id": order_id,
                                                  "status": "Отменена"}).status_code == 200
    assert client.post("/api/replan", json=_delay("12:00", True)).status_code == 200

    plan = client.get(f"/api/plan/{REGION}").json()["data"]
    assert any(order["id"] == order_id for order in plan["orders"])
    assert plan["progress"]["cancelled"] == 1
    reused = client.post("/api/replan", json={
        "region": REGION, "kind": "urgent_order", "at": "12:30", "apply": False,
        "new_order": {"id": order_id, "lat": 55.7, "lon": 37.6, "duration_min": 60,
                      "window_start": "12:30", "window_end": "23:59",
                      "required_skill": "Аварийные работы"}})
    assert reused.status_code == 400


def test_event_before_the_applied_one_is_refused(client):
    assert client.post("/api/replan", json=_delay("13:00", True)).status_code == 200
    answer = client.post("/api/replan", json=_delay("09:30", False))
    assert answer.status_code == 400
    assert "13:00" in answer.json()["error"]["message"]
    assert client.get(f"/api/plan/{REGION}").json()["data"]["clock"] == "13:00"


def test_preview_is_not_applied_after_the_day_changed(client):
    assert client.post("/api/replan", json=_delay("12:00", False)).status_code == 200
    order_id = _first_assigned(client)
    client.post("/api/order/status", json={"region": REGION, "order_id": order_id,
                                           "status": "В пути"})
    answer = client.post("/api/replan", json=_delay("12:00", True))
    assert answer.status_code == 409


def test_step_back_is_labelled_with_what_it_undoes(client):
    order_id = _first_assigned(client)
    client.post("/api/order/status", json={"region": REGION, "order_id": order_id,
                                           "status": "В пути"})
    plan = client.get(f"/api/plan/{REGION}").json()["data"]
    assert plan["undo"][0].startswith(f"Заявка {order_id}")
