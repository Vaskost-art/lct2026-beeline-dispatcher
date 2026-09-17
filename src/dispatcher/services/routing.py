"""Построение и проверка маршрута одного исполнителя.

Общий слой для всех режимов: жадный baseline, оптимизатор, перепланирование
и ручное переназначение считают время и пробег здесь, поэтому цифры на экране
всегда получены одним и тем же способом.

Правила из ТЗ (п. 2.2):
  * НАЧАЛО работ должно попадать во временное окно заявки;
  * работа с учётом времени в пути и длительности должна укладываться в смену;
  * маршрут стартует в базовой точке исполнителя, возврат не требуется.
"""
from __future__ import annotations

from dataclasses import dataclass

from dispatcher.domain import Engineer, Order, Route, Stop
from dispatcher.domain.distance import road_km, travel_minutes


@dataclass
class Leg:
    """Результат попытки поставить заявку в конец маршрута."""

    feasible: bool
    stop: Stop | None = None
    reason: str = ""


def build_leg(engineer: Engineer, prev_lat: float, prev_lon: float,
              ready_at: int, order: Order) -> Leg:
    """Считает визит к `order` из точки (prev_lat, prev_lon) с момента `ready_at`."""
    km = road_km(prev_lat, prev_lon, order.lat, order.lon)
    travel = travel_minutes(km, engineer.vehicle)
    arrival = ready_at + travel

    start = max(arrival, order.window_start)
    wait = start - arrival

    if start > order.window_end:
        return Leg(False, reason="window_closed")

    end = start + order.duration_min
    # work_end уже учитывает перерыв на обед
    if end > engineer.work_end:
        return Leg(False, reason="shift_overflow")

    return Leg(True, Stop(order_id=order.id, arrival=arrival, start=start, end=end,
                          travel_min=travel, travel_km=km, wait_min=wait))


def evaluate_sequence(engineer: Engineer, orders: list[Order]) -> tuple[Route | None, str]:
    """Проверяет и просчитывает маршрут по заданному порядку посещения.

    Возвращает (маршрут, '') либо (None, причина невыполнимости).
    """
    route = Route(engineer_id=engineer.id)
    lat, lon = engineer.lat, engineer.lon
    clock = engineer.shift_start

    for order in orders:
        leg = build_leg(engineer, lat, lon, clock, order)
        if not leg.feasible:
            return None, leg.reason
        route.stops.append(leg.stop)
        lat, lon, clock = order.lat, order.lon, leg.stop.end

    return route, ""


def route_end_state(engineer: Engineer, route: Route,
                    orders_by_id: dict[str, Order]) -> tuple[float, float, int]:
    """Где и когда исполнитель освободится после последней заявки маршрута."""
    if not route.stops:
        return engineer.lat, engineer.lon, engineer.shift_start
    last = route.stops[-1]
    order = orders_by_id[last.order_id]
    return order.lat, order.lon, last.end


def insertion_cost(engineer: Engineer, route: Route, orders_by_id: dict[str, Order],
                   order: Order, position: int) -> tuple[bool, float, Route | None]:
    """Стоимость вставки заявки в позицию `position` маршрута.

    Возвращает (возможно ли, прирост пробега в км, новый маршрут).
    Вставка проверяется полностью: пересчитывается весь хвост маршрута,
    потому что сдвиг времени может выбить из окна следующие заявки.
    """
    current = [orders_by_id[s.order_id] for s in route.stops]
    candidate = current[:position] + [order] + current[position:]
    new_route, _ = evaluate_sequence(engineer, candidate)
    if new_route is None:
        return False, 0.0, None
    return True, new_route.total_km - route.total_km, new_route
