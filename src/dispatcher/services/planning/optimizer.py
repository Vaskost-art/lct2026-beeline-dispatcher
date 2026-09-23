"""Оптимизатор маршрутов на OR-Tools.

Решается VRPTW с ограничениями по навыку, транспорту и смене. Приоритеты
целевой функции сверху вниз: больше назначенных заявок, меньше занятых
исполнителей, меньше пробег.
"""
from __future__ import annotations

import time
from collections.abc import Callable

from ortools.constraint_solver import pywrapcp

from dispatcher.domain import (
    Engineer,
    Order,
    Plan,
    Route,
)
from dispatcher.domain.distance import road_km
from dispatcher.services.planning.baseline import _finalize
from dispatcher.services.planning.costs import (
    DEFAULT_TIME_LIMIT_SEC,
    ENGINEER_FIXED_COST,
)
from dispatcher.services.planning.eligibility import restrict_crews
from dispatcher.services.planning.equipment_limit import limit_bags
from dispatcher.services.planning.extract import routes_from_solution
from dispatcher.services.planning.frozen import pin_prefixes
from dispatcher.services.planning.search import (
    FIRST_SOLUTION,
    METAHEURISTIC,
    SOLUTION_LIMIT,
    _status_name,
)
from dispatcher.services.planning.transit import transit_matrix
from dispatcher.services.planning.urgency import rush_emergencies


def solve_optimized(orders: list[Order], engineers: list[Engineer],
                    time_limit_sec: int = DEFAULT_TIME_LIMIT_SEC,
                    locked: dict[str, str] | None = None,
                    frozen: dict[str, list[str]] | None = None,
                    deadlines: dict[str, int] | None = None,
                    issued: dict[str, dict[str, int]] | None = None) -> Plan:
    """Оптимизация маршрутов через OR-Tools Routing.

    locked - жёсткая привязка order_id -> engineer_id (ручное переназначение
    диспетчером и уже выполненные заявки при перепланировании).
    frozen - префиксы маршрутов, которые нельзя менять (заявки, к которым
    исполнитель уже выехал или которые уже выполнены на момент события).
    deadlines - не позже какого момента начать аварию, поступившую днём.
    issued - выданное утром оборудование: больше него бригада не повезёт.
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

    # Узлы: 0..n_orders-1 - заявки; далее по одному стартовому узлу на каждого
    # исполнителя; последний узел - фиктивный финиш с нулевой стоимостью,
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

    # --- время в пути зависит от транспорта: матрица на каждый вид ---
    # Считается заранее: решатель зовёт колбэк на каждом шаге поиска, и
    # модель поездки по плечам прямо в колбэке замедляла расчёт вчетверо.
    time_cb_by_vehicle: dict[str, int] = {}
    for kind in {engineer.vehicle for engineer in engineers}:
        transit = transit_matrix(km_exact, orders, n_orders, end_node, kind)

        def make_cb(matrix: list[list[int]]) -> Callable[[int, int], int]:
            def time_cb(from_index: int, to_index: int) -> int:
                i: int = manager.IndexToNode(from_index)
                j: int = manager.IndexToNode(to_index)
                return matrix[i][j]
            return time_cb
        time_cb_by_vehicle[kind] = routing.RegisterTransitCallback(make_cb(transit))
    time_cb_indices = [time_cb_by_vehicle[engineer.vehicle] for engineer in engineers]
    for vehicle_id in range(len(engineers)):
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

    rush_emergencies(manager, time_dim, orders, engineers, deadlines or {})

    for vehicle_id, engineer in enumerate(engineers):
        start_index = routing.Start(vehicle_id)
        end_index = routing.End(vehicle_id)
        # Смена могла схлопнуться или вывернуться - например, исполнитель
        # выбыл раньше её начала. Пустой интервал решатель не принимает
        # и падает исключением, поэтому сводим такую смену к нулевой.
        shift_start = engineer.shift_start
        # work_end короче конца смены на перерыв
        shift_end = max(shift_start, engineer.work_end)
        time_dim.CumulVar(start_index).SetRange(shift_start, shift_end)
        time_dim.CumulVar(end_index).SetRange(shift_start, shift_end)
        routing.AddVariableMinimizedByFinalizer(time_dim.CumulVar(start_index))
        routing.AddVariableMinimizedByFinalizer(time_dim.CumulVar(end_index))

    restrict_crews(routing, manager, orders, engineers, locked)
    pin_prefixes(routing, manager, time_dim, orders, engineers, frozen)
    limit_bags(routing, manager, orders, engineers, issued or {})

    # --- параметры поиска ---
    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = FIRST_SOLUTION
    params.local_search_metaheuristic = METAHEURISTIC
    params.time_limit.FromSeconds(max(1, int(time_limit_sec)))
    # Предел по числу улучшений, а не только по времени: за одинаковые
    # секунды разные машины успевают разное, и один и тот же день давал
    # планы на 141 и на 153 км. Диспетчер должен получать один ответ на
    # один вопрос, поэтому поиск останавливается на счётном пределе, а
    # время остаётся страховкой от зависания.
    params.solution_limit = SOLUTION_LIMIT
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
