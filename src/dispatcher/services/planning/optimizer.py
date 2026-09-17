"""Оптимизатор маршрутов на OR-Tools.

Решается VRPTW с ограничениями по навыку, транспорту и смене. Приоритеты
целевой функции сверху вниз: больше назначенных заявок, меньше занятых
исполнителей, меньше пробег.
"""
from __future__ import annotations

import time
from collections.abc import Callable

from ortools.constraint_solver import pywrapcp

from dispatcher.domain import PRIORITY_URGENT, Engineer, Order, Plan, Route
from dispatcher.domain.distance import road_km, travel_minutes
from dispatcher.services.planning.baseline import _finalize
from dispatcher.services.planning.costs import (
    DEFAULT_TIME_LIMIT_SEC,
    DROP_PENALTY_NORMAL,
    DROP_PENALTY_URGENT,
    ENGINEER_FIXED_COST,
)
from dispatcher.services.planning.extract import routes_from_solution
from dispatcher.services.planning.search import FIRST_SOLUTION, METAHEURISTIC, _status_name


def solve_optimized(orders: list[Order], engineers: list[Engineer],
                    time_limit_sec: int = DEFAULT_TIME_LIMIT_SEC,
                    locked: dict[str, str] | None = None,
                    frozen: dict[str, list[str]] | None = None) -> Plan:
    """Оптимизация маршрутов через OR-Tools Routing.

    locked — жёсткая привязка order_id -> engineer_id (ручное переназначение
    диспетчером и уже выполненные заявки при перепланировании).
    frozen — префиксы маршрутов, которые нельзя менять (заявки, к которым
    исполнитель уже выехал или которые уже выполнены на момент события).
    """
    started = time.perf_counter()
    if not orders or not engineers:
        plan = Plan(routes=[Route(engineer_id=e.id) for e in engineers],
                    strategy="optimized", solver_status="EMPTY")
        return _finalize(plan, orders, engineers)

    locked = locked or {}
    frozen = frozen or {}

    n_orders = len(orders)
    n_vehicles = len(engineers)

    # Узлы: 0..n_orders-1 — заявки; далее по одному стартовому узлу на каждого
    # исполнителя; последний узел — фиктивный финиш с нулевой стоимостью,
    # потому что по ТЗ возврат на базу не требуется.
    start_nodes = [n_orders + i for i in range(n_vehicles)]
    end_node = n_orders + n_vehicles

    coords: list[tuple[float, float]] = [(o.lat, o.lon) for o in orders]
    coords += [(e.lat, e.lon) for e in engineers]
    coords.append((0.0, 0.0))                 # фиктивный финиш

    manager = pywrapcp.RoutingIndexManager(len(coords), n_vehicles,
                                           start_nodes, [end_node] * n_vehicles)
    routing = pywrapcp.RoutingModel(manager)

    # --- матрицы расстояний: целые метры для стоимости, точные километры
    # для времени. Время обязано считаться из того же километража, что и в
    # routing.py: расхождение даже в минуту делает маршрут невыполнимым при
    # пересчёте, и весь маршрут исполнителя пропадает.
    size = len(coords)
    dist_m = [[0] * size for _ in range(size)]
    km_exact = [[0.0] * size for _ in range(size)]
    for i in range(size):
        for j in range(size):
            if i == j or end_node in (i, j):
                continue                      # дуги в фиктивный финиш бесплатны
            km = road_km(*coords[i], *coords[j])
            km_exact[i][j] = km
            dist_m[i][j] = int(round(km * 1000))

    def distance_cb(from_index: int, to_index: int) -> int:
        i: int = manager.IndexToNode(from_index)
        j: int = manager.IndexToNode(to_index)
        return dist_m[i][j]

    dist_cb_idx = routing.RegisterTransitCallback(distance_cb)

    # --- время в пути зависит от транспорта, поэтому колбэк свой на каждого ---
    time_cb_indices = []
    for vehicle_id, engineer in enumerate(engineers):
        def make_cb(eng: Engineer) -> Callable[[int, int], int]:
            def time_cb(from_index: int, to_index: int) -> int:
                i = manager.IndexToNode(from_index)
                j = manager.IndexToNode(to_index)
                service = orders[i].duration_min if i < n_orders else 0
                if i == end_node or j == end_node:
                    return service
                travel = travel_minutes(km_exact[i][j], eng.vehicle)
                return service + travel
            return time_cb
        cb_idx = routing.RegisterTransitCallback(make_cb(engineer))
        time_cb_indices.append(cb_idx)
        routing.SetArcCostEvaluatorOfVehicle(dist_cb_idx, vehicle_id)
        routing.SetFixedCostOfVehicle(ENGINEER_FIXED_COST, vehicle_id)

    # --- измерение времени: окна заявок и границы смен ---
    horizon = 24 * 60
    routing.AddDimensionWithVehicleTransits(
        time_cb_indices,
        horizon,          # разрешённое ожидание открытия окна
        horizon,          # верхняя граница накопленного времени
        False,            # накопленное время НЕ обнуляется в начале маршрута
        "Time",
    )
    time_dim = routing.GetDimensionOrDie("Time")

    for node, order in enumerate(orders):
        index = manager.NodeToIndex(node)
        # CumulVar в узле = момент НАЧАЛА работ; по ТЗ он обязан попасть в окно
        time_dim.CumulVar(index).SetRange(order.window_start, order.window_end)

    for vehicle_id, engineer in enumerate(engineers):
        start_index = routing.Start(vehicle_id)
        end_index = routing.End(vehicle_id)
        # Смена могла схлопнуться или вывернуться — например, исполнитель
        # выбыл раньше её начала. Пустой интервал решатель не принимает
        # и падает исключением, поэтому сводим такую смену к нулевой.
        shift_start = engineer.shift_start
        # work_end короче конца смены на перерыв
        shift_end = max(shift_start, engineer.work_end)
        time_dim.CumulVar(start_index).SetRange(shift_start, shift_end)
        time_dim.CumulVar(end_index).SetRange(shift_start, shift_end)
        routing.AddVariableMinimizedByFinalizer(time_dim.CumulVar(start_index))
        routing.AddVariableMinimizedByFinalizer(time_dim.CumulVar(end_index))

    # --- ограничения «Навык» и «Ресурс»: список допустимых исполнителей ---
    for node, order in enumerate(orders):
        index = manager.NodeToIndex(node)
        allowed = [v for v, e in enumerate(engineers) if e.can_do(order)]

        pinned = locked.get(order.id)
        if pinned is not None:
            allowed = [v for v, e in enumerate(engineers)
                       if e.id == pinned and v in allowed]

        if not allowed:
            # Заявку не может взять никто. Домен из одного значения -1
            # означает «обязана остаться неназначенной»: без этого солвер
            # вправе отдать её любому исполнителю, и план нарушит
            # ограничение по навыку или по транспорту.
            routing.VehicleVar(index).SetValues([-1])
            routing.AddDisjunction([index], 0)
            continue

        # -1 в домене означает «заявка не назначена»: без него солвер не смог бы
        # снять заявку, для которой не хватает ресурсов.
        routing.VehicleVar(index).SetValues([-1] + allowed)
        penalty = (DROP_PENALTY_URGENT if order.priority == PRIORITY_URGENT
                   else DROP_PENALTY_NORMAL)
        routing.AddDisjunction([index], penalty)

    # --- замороженные префиксы маршрутов при перепланировании ---
    order_index = {o.id: i for i, o in enumerate(orders)}
    for engineer_id, prefix in frozen.items():
        found = next((v for v, e in enumerate(engineers) if e.id == engineer_id), None)
        if found is None:
            continue
        vehicle_id = found
        chain = [order_index[oid] for oid in prefix if oid in order_index]
        prev_index = routing.Start(vehicle_id)
        for node in chain:
            index = manager.NodeToIndex(node)
            routing.solver().Add(routing.NextVar(prev_index) == index)
            routing.VehicleVar(index).SetValue(vehicle_id)
            prev_index = index

    # --- параметры поиска ---
    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = FIRST_SOLUTION
    params.local_search_metaheuristic = METAHEURISTIC
    params.time_limit.FromSeconds(max(1, int(time_limit_sec)))
    params.log_search = False

    solution = routing.SolveWithParameters(params)
    elapsed = round(time.perf_counter() - started, 3)

    status_name = _status_name(routing.status())

    if solution is None:
        plan = Plan(routes=[Route(engineer_id=e.id) for e in engineers],
                    strategy="optimized", solver_status=status_name,
                    solve_seconds=elapsed)
        return _finalize(plan, orders, engineers)

    routes = routes_from_solution(routing, manager, solution, orders, engineers)

    plan = Plan(routes=routes, strategy="optimized",
                solver_status=status_name, solve_seconds=elapsed)
    return _finalize(plan, orders, engineers)
