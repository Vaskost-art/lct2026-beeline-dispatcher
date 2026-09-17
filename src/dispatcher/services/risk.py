"""Прогноз опозданий: насколько план устойчив к задержкам (ТЗ п. 2.5).

План, построенный по нормативам, всегда выглядит выполнимым. В реальном дне
работы затягиваются, дорога занимает больше, абонент не открывает дверь.
Диспетчеру важно знать заранее, где план порвётся первым.

Считаем две вещи, обе проверяемые прямым пересчётом маршрута:

  * **запас прочности** — сколько минут задержки маршрут выдержит, прежде чем
    какая-то заявка выпадет из своего окна или выйдет за смену. Считается
    отдельно для маршрута целиком и для каждого визита в нём;
  * **последствия просадки** — что произойдёт, если КАЖДАЯ работа в плане
    затянется на заданное число минут: сколько заявок сорвётся и какие именно.

Запас считается двоичным поиском по прямой симуляции маршрута: никаких
вероятностных моделей, только «при какой задержке правило ТЗ перестаёт
выполняться». Поэтому цифру можно проверить руками.
"""
from __future__ import annotations

from typing import TypedDict

from dispatcher.domain import Engineer, Order
from dispatcher.domain.distance import road_km, travel_minutes

# Границы уровней риска по запасу прочности, минуты.
RISK_HIGH_BELOW = 20
RISK_MEDIUM_BELOW = 60

RISK_HIGH = "высокий"
RISK_MEDIUM = "средний"
RISK_LOW = "низкий"

# Максимальная проверяемая задержка: дальше считать бессмысленно, день кончится.
DELAY_CAP_MIN = 240


def risk_level(tolerance_min: int) -> str:
    if tolerance_min < RISK_HIGH_BELOW:
        return RISK_HIGH
    if tolerance_min < RISK_MEDIUM_BELOW:
        return RISK_MEDIUM
    return RISK_LOW


def simulate(engineer: Engineer, sequence: list[Order],
              delay: int = 0, at_index: int = 0,
              overrun_per_job: int = 0) -> int | None:
    """Проигрывает маршрут с задержкой и возвращает индекс первого срыва.

    delay            — разовая задержка, добавляемая перед визитом at_index;
    overrun_per_job  — на сколько минут затягивается каждая работа.
    Возвращает None, если маршрут остаётся выполнимым.
    """
    lat, lon = engineer.lat, engineer.lon
    clock = engineer.shift_start

    for index, order in enumerate(sequence):
        if index == at_index:
            clock += delay

        km = road_km(lat, lon, order.lat, order.lon)
        arrival = clock + travel_minutes(km, engineer.vehicle)
        start = max(arrival, order.window_start)
        if start > order.window_end:
            return index

        end = start + order.duration_min + overrun_per_job
        if end > engineer.work_end:
            return index

        clock = end
        lat, lon = order.lat, order.lon

    return None


def _max_delay(engineer: Engineer, sequence: list[Order],
               at_index: int) -> int:
    """Наибольшая задержка перед визитом at_index, которую маршрут выдержит."""
    if simulate(engineer, sequence, DELAY_CAP_MIN, at_index) is None:
        return DELAY_CAP_MIN
    low, high = 0, DELAY_CAP_MIN
    while low < high:
        mid = (low + high + 1) // 2
        if simulate(engineer, sequence, mid, at_index) is None:
            low = mid
        else:
            high = mid - 1
    return low


class StopRisk(TypedDict):
    """Запас прочности одного визита."""

    order_id: str
    position: int
    tolerance_min: int
    risk: str
    breaks_order_id: str | None
    window: str


def route_risk(engineer: Engineer, sequence: list[Order]) -> dict:
    """Запас прочности маршрута целиком и каждого визита в нём."""
    if not sequence:
        return {"engineer_id": engineer.id, "used": False, "stops": []}

    # Задержка на старте — самый мягкий случай: её поглощают ожидания открытия
    # окон дальше по маршруту. Поэтому отдельно считаем запас на выезд и
    # отдельно — запас в каждой точке маршрута.
    start_tolerance = _max_delay(engineer, sequence, 0)

    stops: list[StopRisk] = []
    for index, order in enumerate(sequence):
        stop_tolerance = _max_delay(engineer, sequence, index)
        stop_break = simulate(engineer, sequence, stop_tolerance + 1, index)
        stops.append({
            "order_id": order.id,
            "position": index + 1,
            "tolerance_min": stop_tolerance,
            "risk": risk_level(stop_tolerance),
            "breaks_order_id": (sequence[stop_break].id
                                if stop_break is not None else None),
            "window": order.window_text,
        })

    # Прочность маршрута определяется его слабейшим звеном, а не самым
    # удобным местом для задержки.
    weakest_stop = min(stops, key=lambda s: s["tolerance_min"])
    tolerance = weakest_stop["tolerance_min"]

    return {
        "engineer_id": engineer.id,
        "used": True,
        "tolerance_min": tolerance,
        "start_tolerance_min": start_tolerance,
        "risk": risk_level(tolerance),
        "weakest_order_id": weakest_stop["order_id"],
        "weakest_position": weakest_stop["position"],
        "breaks_order_id": weakest_stop["breaks_order_id"],
        "stops": stops,
        "text": _route_text(engineer, tolerance, weakest_stop),
    }


def _route_text(engineer: Engineer, tolerance: int, weakest: StopRisk) -> str:
    """Текст показывается внутри блока самого маршрута, поэтому имя
    исполнителя в нём не повторяется."""
    if tolerance >= DELAY_CAP_MIN:
        return (f"Маршрут выдержит любую разумную задержку: окна и смена "
                f"оставляют больше {DELAY_CAP_MIN // 60} часов запаса.")

    head = (f"Слабое место — визит №{weakest['position']} "
            f"(заявка {weakest['order_id']}, окно {weakest['window']}): "
            f"выдержит задержку не больше {tolerance} мин.")
    if weakest["breaks_order_id"] and weakest["breaks_order_id"] != weakest["order_id"]:
        head += f" Дальше сорвётся заявка {weakest['breaks_order_id']}."
    else:
        head += " Дальше сорвётся она сама."
    return head
