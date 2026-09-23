"""Заготовки для тестов оборудования: две бригады, одна везёт два роутера."""
from dispatcher.domain import Order, Plan, Route, Stop
from dispatcher.domain.equipment import ROUTER


def bag_order(order_id: str, equipment: list[str]) -> Order:
    return Order(id=order_id, lat=55.7, lon=37.6, address="", district="",
                 duration_min=30, window_start=600, window_end=720,
                 priority="Обычная", required_skill="Работы на подключение",
                 equipment=equipment)


def bag_stop(order_id: str) -> Stop:
    return Stop(order_id=order_id, arrival=600, start=600, end=630,
                travel_min=10, travel_km=2.0, wait_min=0)


def bag_day():
    """Бригада 1 везёт два роутера, бригада 2 не везёт ничего."""
    orders = [bag_order("1", [ROUTER]), bag_order("2", [ROUTER]), bag_order("3", [])]
    plan = Plan(routes=[
        Route(engineer_id="Бригада 1", stops=[bag_stop("1"), bag_stop("2")]),
        Route(engineer_id="Бригада 2", stops=[bag_stop("3")]),
    ])
    return plan, orders

