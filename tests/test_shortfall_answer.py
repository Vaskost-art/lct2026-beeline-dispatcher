"""Ответ сервиса на непомещающиеся заявки: «нужно ещё N исполнителей»."""
import warnings

from fastapi.testclient import TestClient

from dispatcher.api.app import app

warnings.filterwarnings("ignore")


def _plan(region: str) -> dict:
    with TestClient(app) as client:
        answer = client.post("/api/plan",
                             json={"region": region, "strategy": "greedy"})
        assert answer.status_code == 200
        return answer.json()["data"]


def test_plan_says_how_many_crews_are_missing():
    payload = _plan("vostok")

    assert "shortfall" in payload
    shortfall = payload["shortfall"]
    assert isinstance(shortfall["missing"], int)
    assert shortfall["missing"] >= 0


def test_unexplained_orders_get_a_reason_that_is_not_about_people():
    """Заявку, которую не берёт даже свободная бригада, нельзя объяснить людьми."""
    payload = _plan("yugo_vostok")
    shortfall = payload["shortfall"]

    if shortfall["still_unassigned"]:
        assert shortfall["reason"]
        assert "окно" in shortfall["reason"]
