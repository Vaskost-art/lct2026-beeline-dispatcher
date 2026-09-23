"""Предпросмотр новой заявки собирается по дню предпросмотра, а не по текущему.

Ответ брал заявки и бригады из текущей версии дня, где новой заявки ещё нет,
и падал с 500 на объяснении маршрута, в который она встала.
"""
import warnings

from fastapi.testclient import TestClient

from dispatcher.api.app import app

warnings.filterwarnings("ignore")

NEW = {"id": "ПРЕДПРОСМОТР-1", "lat": 55.705, "lon": 37.79, "address": "Кузьминки",
       "district": "Кузьминки", "duration_min": 30, "window_start": "12:00",
       "window_end": "23:59", "required_skill": "Локальные работы"}


def test_preview_of_new_order_answers_and_shows_it():
    with TestClient(app) as client:
        assert client.post("/api/plan", json={"region": "vostok",
                                              "strategy": "greedy"}).status_code == 200
        answer = client.post("/api/replan", json={
            "region": "vostok", "kind": "urgent_order", "at": "12:00",
            "mode": "minimal", "apply": False, "new_order": NEW})
        current = client.get("/api/plan/vostok").json()["data"]

    assert answer.status_code == 200, answer.text
    data = answer.json()["data"]
    assert any(order["id"] == NEW["id"] for order in data["orders"])
    placed = any(stop["order_id"] == NEW["id"]
                 for route in data["routes"] for stop in route["stops"])
    assert placed, "заявка должна встать: иначе тест не проверяет объяснение маршрута"
    assert not any(order["id"] == NEW["id"] for order in current["orders"])
