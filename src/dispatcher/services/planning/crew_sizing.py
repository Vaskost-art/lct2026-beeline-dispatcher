"""Сколько бригад нужно участку и как они выглядят.

В синтетических данных исполнителей нет. Постановщик сказал прямо: число
исполнителей заранее не задано, их можно добавлять, а правильный ответ
сервиса на непомещающиеся заявки - «нужно ещё N исполнителей».

Оценка снизу считается по двум ограничениям сразу: сколько бригад нужно по
объёму работ за смену и сколько нужно в самый плотный час. Второе обычно
жёстче: заявки с окном 10:00-12:00 нельзя сделать одна за другой.
"""
from __future__ import annotations

from collections.abc import Callable

from dispatcher.domain import Engineer, Order, Plan, shifts
from dispatcher.domain.crew_profiles import skills_for_index, vehicle_for_index
from dispatcher.domain.text import plural

#: Как зовут планировщик: заявки и бригады на входе, план на выходе.
type Solver = Callable[[list[Order], list[Engineer]], Plan]

#: Запас на дорогу между заявками при оценке по объёму работ, доля от времени
#: работ. Оценка грубая и нужна только как нижняя граница.
TRAVEL_ALLOWANCE = 0.35


def _day_bounds(orders: list[Order]) -> tuple[int, int]:
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
    start, end = _day_bounds(orders)
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
    start, end = _day_bounds(orders)
    need_car = min(count, cars_needed(orders))
    crews: list[Engineer] = []
    for index in range(count):
        number = index + 1
        crews.append(Engineer(
            id=f"Бригада {number}",
            name=f"Бригада {number}",
            lat=office_lat,
            lon=office_lon,
            start_address=office_address or "Офис участка",
            shift_start=start,
            shift_end=end,
            skills=skills_for_index(index, count),
            vehicle=vehicle_for_index(index, count, need_car),
            break_min=shifts.break_minutes(start, end),
        ))
    return crews


#: Сколько бригад подряд можно добавить без единой новой заявки, прежде чем
#: признать, что дело не в людях.
FRUITLESS_LIMIT = 2

#: Дальше этого числа бригад подбор не идёт: участок такого размера означает
#: ошибку в данных, а не нехватку людей.
MAX_EXTRA_CREWS = 20


def _next_crew(index: int, unassigned: list[Order], orders: list[Order],
               office_lat: float, office_lon: float, office_address: str) -> Engineer:
    """Бригада под самую частую потребность среди нераспределённых заявок."""
    start, end = _day_bounds(orders)
    skills = sorted({o.required_skill for o in unassigned})[:3] or None
    needs_car = any(o.required_vehicle for o in unassigned)
    number = index + 1
    return Engineer(
        id=f"Бригада {number}",
        name=f"Бригада {number}",
        lat=office_lat,
        lon=office_lon,
        start_address=office_address or "Офис участка",
        shift_start=start,
        shift_end=end,
        skills=skills or skills_for_index(index, index + 1),
        vehicle="Автомобиль" if needs_car else vehicle_for_index(index, index + 1, 0),
        break_min=shifts.break_minutes(start, end),
    )


def crews_shortfall(orders: list[Order], crews: list[Engineer],
                    solve: Solver,
                    office_lat: float, office_lon: float,
                    office_address: str) -> dict[str, object]:
    """Сколько ещё бригад нужно, чтобы разошлись оставшиеся заявки.

    Бригады добавляются по одной, пока каждая новая забирает хотя бы одну
    заявку. Если две подряд не забрали ничего, причина не в числе людей, и
    об этом говорится прямо: иначе диспетчер будет искать людей там, где
    мешает временное окно.
    """
    plan = solve(orders, crews)
    if not plan.unassigned:
        # Форма ответа одна на обе ветки: экран не должен гадать, есть ли
        # ключ, и подставлять за сервис значение по умолчанию.
        return {"missing": 0, "assigned": plan.assigned_count,
                "still_unassigned": 0,
                "reason": "", "limited_by_people": False}

    extended = list(crews)
    best = plan.assigned_count
    useful = 0          # бригады, каждая из которых забрала хотя бы заявку
    fruitless = 0       # добавленные подряд и не забравшие ничего

    while len(extended) - len(crews) < MAX_EXTRA_CREWS and fruitless < FRUITLESS_LIMIT:
        unassigned_ids = {u.order_id for u in plan.unassigned}
        pending = [o for o in orders if o.id in unassigned_ids]
        extended = extended + [_next_crew(len(extended), pending, orders,
                                          office_lat, office_lon, office_address)]
        plan = solve(orders, extended)
        if plan.assigned_count > best:
            best = plan.assigned_count
            useful = len(extended) - len(crews)
            fruitless = 0
        else:
            fruitless += 1
        if not plan.unassigned:
            break

    still_left = len(orders) - best
    return {
        "missing": useful,
        "assigned": best,
        "still_unassigned": still_left,
        # Заявки, которые не берёт даже свободная бригада, упираются не в
        # число людей: иначе диспетчер будет искать людей там, где мешает окно.
        "reason": (f"Ещё {still_left} "
                   f"{plural(still_left, 'заявку', 'заявки', 'заявок')} "
                   "не берёт ни одна бригада: мешает временное окно или "
                   "требования заявки, а не число людей."
                   if still_left else ""),
        "limited_by_people": useful > 0,
    }
