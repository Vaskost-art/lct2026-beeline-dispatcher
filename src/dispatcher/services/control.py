"""План по факту диспетчера, восстановленный из контрольной выгрузки.

Служит ориентиром «как было в жизни». Заказчик прямо сказал, что это не
эталон качества: сравнение с ним не является метрикой решения.
"""
from __future__ import annotations

from dispatcher.domain import Engineer, Order, Plan, Route, Stop, hhmm
from dispatcher.domain.distance import road_km
from dispatcher.domain.travel import plan_trip
from dispatcher.services.routing import evaluate_sequence


def control_plan(orders: list[Order], engineers: list[Engineer]) -> tuple[Plan, dict]:
    """Восстанавливает фактическое распределение живого диспетчера.

    В выгрузке есть колонка «Бригада» — кто реально выполнял заявку, но нет
    порядка объезда. Принимаем самый естественный порядок: по времени начала
    временного окна. Пробег при этом считается тем же кодом, что и для наших
    планов, поэтому сравнение честное.

    Важная оговорка: длительности работ — наш норматив, а не факт, поэтому
    фактический план проверяется на выполнимость «мягко»: если по нашим
    нормативам он не укладывается в смену, мы всё равно показываем его
    пробег и число людей, но помечаем это в отчёте.
    """
    engineer_by_id = {e.id: e for e in engineers}
    grouped: dict[str, list[Order]] = {}
    unknown: list[str] = []

    for order in orders:
        crew = order.control_engineer
        if not crew:
            unknown.append(order.id)
            continue
        if crew not in engineer_by_id:
            unknown.append(order.id)
            continue
        grouped.setdefault(crew, []).append(order)

    routes: list[Route] = []
    infeasible: list[str] = []
    for engineer in engineers:
        sequence = sorted(grouped.get(engineer.id, []),
                          key=lambda o: (o.window_start, o.window_end))
        if not sequence:
            routes.append(Route(engineer_id=engineer.id))
            continue
        route, reason = evaluate_sequence(engineer, sequence)
        if route is None:
            # мягкий режим: считаем маршрут без проверки окон и смены
            route = _relaxed_route(engineer, sequence)
            infeasible.append(engineer.id)
        routes.append(route)

    plan = Plan(routes=routes, strategy="control", solver_status="FACT")

    # Насколько фактический план вообще совместим с правилами ТЗ.
    order_by_id = {o.id: o for o in orders}
    window_violations = []
    shift_overflow = []
    for route in routes:
        found = engineer_by_id.get(route.engineer_id)
        if found is None:
            continue
        engineer = found
        for stop in route.stops:
            order = order_by_id[stop.order_id]
            if stop.start > order.window_end:
                window_violations.append({
                    "order_id": order.id,
                    "engineer_id": route.engineer_id,
                    "window": order.window_text,
                    "planned_start": hhmm(stop.start),
                    "late_by_min": stop.start - order.window_end,
                })
            # work_end, а не shift_end: наши планы проверяются именно им, и
            # судить факт более мягким правилом значит давать ему фору в обед
            if engineer and stop.end > engineer.work_end:
                shift_overflow.append({
                    "order_id": order.id,
                    "engineer_id": route.engineer_id,
                    "shift_end": hhmm(engineer.work_end),
                    "planned_end": hhmm(stop.end),
                    "over_by_min": stop.end - engineer.work_end,
                })

    # Сколько заявок фактически ставилось одной бригаде в одно окно.
    per_window: dict[tuple[str, int], int] = {}
    for order in orders:
        if order.control_engineer:
            key = (order.control_engineer, order.window_start)
            per_window[key] = per_window.get(key, 0) + 1
    max_in_window = max(per_window.values()) if per_window else 0

    report = {
        "orders_without_crew": unknown,
        "engineers_over_norm": infeasible,
        "window_violations": window_violations,
        "shift_overflow": shift_overflow,
        "max_orders_per_window_per_crew": max_in_window,
        "note": "Фактическое распределение из колонки «Бригада». Порядок объезда "
                "принят по времени начала окна — в данных его нет. "
                "Факт не является допустимым планом по правилам ТЗ: одной бригаде "
                f"ставилось до {max_in_window} заявок в одно двухчасовое окно, "
                "тогда как ТЗ требует, чтобы начало работ попадало внутрь окна. "
                "Поэтому сравнение по числу назначенных заявок некорректно, "
                "а показательно сравнение по числу задействованных людей и по "
                "километрам на одну назначенную заявку.",
    }
    return plan, report


def _relaxed_route(engineer: Engineer, sequence: list[Order]) -> Route:
    """Пробег и времена без проверки окон и смены — только для факта."""

    route = Route(engineer_id=engineer.id)
    lat, lon, clock = engineer.lat, engineer.lon, engineer.shift_start
    for order in sequence:
        km = road_km(lat, lon, order.lat, order.lon)
        trip = plan_trip(km, engineer.vehicle)
        travel = trip.minutes
        arrival = clock + travel
        start = max(arrival, order.window_start)
        end = start + order.duration_min
        route.stops.append(Stop(order_id=order.id, arrival=arrival, start=start,
                                end=end, travel_min=travel, travel_km=km,
                                wait_min=start - arrival,
                                travel_text=trip.text,
                                travel_mode=trip.mode_text))
        lat, lon, clock = order.lat, order.lon, end
    return route
