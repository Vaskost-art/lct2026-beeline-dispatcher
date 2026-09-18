"""Ведомость на выдачу: что бригада забирает в офисе утром."""
from dispatcher.domain import Order, Plan, Route, Stop
from dispatcher.domain.equipment import ROUTER, TV_BOX
from dispatcher.services.equipment import pickup_list


def _order(order_id: str, equipment: list[str]) -> Order:
    return Order(id=order_id, lat=55.7, lon=37.6, address="", district="",
                 duration_min=30, window_start=600, window_end=720,
                 priority="Обычная", required_skill="Локальные работы",
                 equipment=equipment)


def _stop(order_id: str) -> Stop:
    return Stop(order_id=order_id, arrival=600, start=600, end=630,
                travel_min=10, travel_km=2.0, wait_min=0)


def test_pickup_counts_equipment_of_the_route():
    orders = [_order("1", [ROUTER]), _order("2", [ROUTER, TV_BOX]),
              _order("3", [])]
    plan = Plan(routes=[Route(engineer_id="Бригада 1",
                              stops=[_stop("1"), _stop("2"), _stop("3")])])

    rows = pickup_list(plan, orders)

    assert len(rows) == 1
    assert rows[0]["engineer_id"] == "Бригада 1"
    assert rows[0]["items"] == {ROUTER: 2, TV_BOX: 1}
    assert rows[0]["total"] == 3
    assert "2" in rows[0]["text"] and ROUTER.lower() in rows[0]["text"].lower()


def test_route_without_equipment_is_not_listed():
    """Бригаде без оборудования в офис заходить незачем."""
    orders = [_order("1", [])]
    plan = Plan(routes=[Route(engineer_id="Бригада 1", stops=[_stop("1")])])

    assert pickup_list(plan, orders) == []


def test_plan_response_carries_equipment_and_pickup():
    """Ответ с планом несёт оборудование заявок и ведомость на выдачу."""
    import warnings

    from fastapi.testclient import TestClient

    from dispatcher.api.app import app

    warnings.filterwarnings("ignore")
    with TestClient(app) as client:
        answer = client.post("/api/plan",
                             json={"region": "vostok", "strategy": "greedy"})
        assert answer.status_code == 200
        payload = answer.json()

    assert "pickup" in payload
    assert any(order.get("equipment") for order in payload["orders"])
    if payload["pickup"]:
        row = payload["pickup"][0]
        assert row["total"] > 0
        assert row["text"]
