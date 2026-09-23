"""Сколько бригад нужно участку и как они выглядят.

В синтетических данных исполнителей нет. Постановщик сказал прямо: число
исполнителей заранее не задано, их можно добавлять, а правильный ответ
сервиса на непомещающиеся заявки - «нужно ещё N исполнителей».

Оценка снизу считается по двум ограничениям сразу: сколько бригад нужно по
объёму работ за смену и сколько нужно в самый плотный час. Второе обычно
жёстче: заявки с окном 10:00-12:00 нельзя сделать одна за другой.
"""
from __future__ import annotations

from dispatcher.domain import Engineer, Order, shifts
from dispatcher.domain.crew_profiles import assign_vehicles, skills_for_index

#: Запас на дорогу между заявками при оценке по объёму работ, доля от времени
#: работ. Оценка грубая и нужна только как нижняя граница.
TRAVEL_ALLOWANCE = 0.35


def day_bounds(orders: list[Order]) -> tuple[int, int]:
    """Границы смены участка по окнам заявок."""
    if not orders:
        return shifts.SHIFT_EARLIEST, shifts.SHIFT_EARLIEST + shifts.SHIFT_MIN_LENGTH_MIN
    first = min(o.window_start for o in orders)
    last = min(max(o.window_end for o in orders), shifts.SHIFT_LATEST)
    return shifts.shift_bounds(first, last)


def crews_by_workload(orders: list[Order], work_minutes: int) -> int:
    """Сколько бригад нужно, чтобы успеть весь объём работ за смену."""
    if work_minutes <= 0:
        return 0
    total = sum(o.duration_min for o in orders) * (1 + TRAVEL_ALLOWANCE)
    return max(1, -(-int(total) // work_minutes))


def crews_by_peak(orders: list[Order]) -> int:
    """Сколько бригад нужно в самый плотный час.

    Заявка занимает бригаду на всё своё окно: если в одно окно попадает
    двенадцать заявок, меньше чем двенадцатью бригадами их не закрыть, сколько
    бы свободного времени ни было в остальной день.
    """
    if not orders:
        return 0
    peak = 0
    for probe in sorted({o.window_start for o in orders}):
        capacity = 0.0
        for order in orders:
            if order.window_start <= probe < order.window_end:
                span = max(1, order.window_end - order.window_start)
                # Сколько заявок такой длительности бригада успеет в этом окне.
                capacity += order.duration_min / span
        peak = max(peak, int(capacity + 0.999))
    return peak


def estimate_crews(orders: list[Order]) -> dict[str, int]:
    """Нижняя оценка числа бригад с разбором, откуда она взялась."""
    start, end = day_bounds(orders)
    work_minutes = max(1, end - start - shifts.break_minutes(start, end))
    by_workload = crews_by_workload(orders, work_minutes)
    by_peak = crews_by_peak(orders)
    return {
        "by_workload": by_workload,
        "by_peak": by_peak,
        "recommended": max(by_workload, by_peak),
        "work_minutes": work_minutes,
        "shift_start": start,
        "shift_end": end,
    }


def cars_needed(orders: list[Order]) -> int:
    """Сколько бригад обязаны быть на автомобиле.

    Считается по самому плотному окну среди заявок, где машина обязательна:
    меньшим числом машин такие заявки одновременно не закрыть.
    """
    with_car = [o for o in orders if o.required_vehicle]
    if not with_car:
        return 0
    return max(1, crews_by_peak(with_car))


def build_crews(count: int, orders: list[Order], office_lat: float,
                office_lon: float, office_address: str) -> list[Engineer]:
    """Собирает `count` бригад участка со стартом из офиса.

    Бригада начинает день в офисе участка: там она получает оборудование.
    """
    start, end = day_bounds(orders)
    skills = [skills_for_index(index, count) for index in range(count)]
    vehicles = assign_vehicles(skills, orders, min(count, cars_needed(orders)))
    return [Engineer(id=f"Бригада {index + 1}", name=f"Бригада {index + 1}",
                     lat=office_lat, lon=office_lon,
                     start_address=office_address or "Центр заявок участка",
                     shift_start=start, shift_end=end, skills=skills[index],
                     vehicle=vehicles[index],
                     break_min=shifts.break_minutes(start, end))
            for index in range(count)]
