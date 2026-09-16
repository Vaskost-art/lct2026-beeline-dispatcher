"""Метрики плана и сравнение вариантов.

Обязательные метрики ТЗ (п. 2.3):
  * количество уникальных исполнителей, которым назначена хотя бы одна заявка;
  * пробег по маршруту каждого исполнителя — отдельно и суммарно по плану.

Дополнительно считаем то, что помогает диспетчеру: долю назначенных заявок,
время в пути, загрузку смены и сравнение с фактическим распределением людей.
"""
from __future__ import annotations

from domain import Engineer, Order, Plan, Route, hhmm
from routing import evaluate_sequence


def plan_metrics(plan: Plan, orders: list[Order],
                 engineers: list[Engineer]) -> dict:
    engineer_by_id = {e.id: e for e in engineers}
    total = len(orders)

    per_engineer = []
    for route in plan.routes:
        if not route.is_used:
            continue
        engineer = engineer_by_id.get(route.engineer_id)
        # рабочее время без обеда: иначе загрузка занижена и маршрут,
        # упёршийся в потолок смены, выглядит как «есть куда добавить»
        shift_len = (engineer.work_end - engineer.shift_start) if engineer else 0
        busy = route.total_work_min + route.total_travel_min
        per_engineer.append({
            "engineer_id": route.engineer_id,
            "orders": len(route.stops),
            "km": round(route.total_km, 2),
            "travel_min": route.total_travel_min,
            "work_min": route.total_work_min,
            "first_start": hhmm(route.stops[0].start),
            "last_end": hhmm(route.stops[-1].end),
            "utilization": round(busy / shift_len, 3) if shift_len else 0.0,
        })
    per_engineer.sort(key=lambda r: -r["km"])

    assigned = plan.assigned_count
    travel_min = sum(r.total_travel_min for r in plan.routes)
    work_min = sum(r.total_work_min for r in plan.routes)

    return {
        "strategy": plan.strategy,
        # --- обязательные метрики ТЗ ---
        "used_engineers": plan.used_engineers,
        "total_km": round(plan.total_km, 2),
        "km_per_engineer": per_engineer,
        # --- вспомогательные ---
        "orders_total": total,
        "orders_assigned": assigned,
        "orders_unassigned": total - assigned,
        "assigned_share": round(assigned / total, 3) if total else 0.0,
        "engineers_available": len(engineers),
        "total_travel_min": travel_min,
        "total_work_min": work_min,
        "travel_share": round(travel_min / (travel_min + work_min), 3)
                        if (travel_min + work_min) else 0.0,
        "avg_km_per_order": round(plan.total_km / assigned, 2) if assigned else 0.0,
        "solver_status": plan.solver_status,
        "solve_seconds": plan.solve_seconds,
    }


def compare(candidate: dict, reference: dict) -> dict:
    """Разница по обязательным метрикам: «наш план против точки отсчёта»."""
    def delta(key: str) -> float:
        return round(candidate[key] - reference[key], 2)

    def pct(key: str) -> float | None:
        base = reference[key]
        return round((candidate[key] - base) / base * 100, 1) if base else None

    return {
        "reference_strategy": reference["strategy"],
        "candidate_strategy": candidate["strategy"],
        "orders_assigned_delta": delta("orders_assigned"),
        "used_engineers_delta": delta("used_engineers"),
        "used_engineers_pct": pct("used_engineers"),
        "total_km_delta": delta("total_km"),
        "total_km_pct": pct("total_km"),
        # Суммарный пробег несопоставим между планами, закрывающими разное
        # число заявок: план, раздавший вдвое меньше работы, «экономит»
        # километры просто потому, что многого не делает. Сопоставима
        # удельная величина — километры на одну назначенную заявку.
        "km_per_order_delta": delta("avg_km_per_order"),
        "km_per_order_pct": pct("avg_km_per_order"),
    }


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
        engineer = engineer_by_id.get(route.engineer_id)
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
    from geo import road_km, travel_minutes
    from domain import Stop

    route = Route(engineer_id=engineer.id)
    lat, lon, clock = engineer.lat, engineer.lon, engineer.shift_start
    for order in sequence:
        km = road_km(lat, lon, order.lat, order.lon)
        travel = travel_minutes(km, engineer.vehicle)
        arrival = clock + travel
        start = max(arrival, order.window_start)
        end = start + order.duration_min
        route.stops.append(Stop(order_id=order.id, arrival=arrival, start=start,
                                end=end, travel_min=travel, travel_km=km,
                                wait_min=start - arrival))
        lat, lon, clock = order.lat, order.lon, end
    return route
