"""Оптимизатор маршрутов на OR-Tools.

Решается VRPTW с ограничениями по навыку, транспорту и смене. Приоритеты
целевой функции сверху вниз: больше назначенных заявок, меньше занятых
исполнителей, меньше пробег.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from dispatcher.domain import PRIORITY_URGENT, Engineer, Order, Plan, Route
from dispatcher.domain.distance import road_km, travel_minutes
from dispatcher.services.planning.baseline import _finalize
from dispatcher.services.planning.costs import (
    DEFAULT_TIME_LIMIT_SEC,
    DROP_PENALTY_NORMAL,
    DROP_PENALTY_URGENT,
    ENGINEER_FIXED_COST,
)
from dispatcher.services.routing import evaluate_sequence

_STATUS_VALUES = [
    value
    for enum_type in routing_enums_pb2.RoutingSearchStatus.DESCRIPTOR.enum_types
    for value in enum_type.values
]

# Настройки поиска вынесены сюда, чтобы их можно было перебирать замером,
# а не править по месту (scripts/benchmark.py).
#
# Выбор не умозрительный: эвристики первого решения перебраны замером на всех
# трёх районах, перебор воспроизводится командой
# `python3 scripts/benchmark.py --heuristics`.
#
# Здесь был SAVINGS — его выбрали, пока координаты были приблизительными.
# После геокодирования замер повторён (по три прогона на район, 15 с), и выбор
# сменился. Оценка — целевая функция, объявленная прямо над этим блоком:
# снятая заявка 5 000 000, бригада 120 000, километр 1 000.
#
#   Район        эвристика                   заявки  бригад     км     оценка
#   Восток       SAVINGS                     62/62/62   11    145.5   51 465 500
#                CHRISTOFIDES                62/62/62  10-11  154-172 51 474 120
#                LOCAL_CHEAPEST_INSERTION    61/61/62   11    143-153 56 463 540
#   Юго-восток   SAVINGS                     70/70/70   12    169.6   81 609 630
#                CHRISTOFIDES                71/71/71   12    192.6   76 632 620
#                LOCAL_CHEAPEST_INSERTION    72/72/72   12    198.9   71 638 910
#   Югоцентр     SAVINGS                     53/53/53    9    117-123 16 197 350
#                CHRISTOFIDES                52/52/52    9     84.7   21 164 660
#                LOCAL_CHEAPEST_INSERTION    53/53/53    9    100.4   16 180 420
#
# Сумма медиан: LOCAL_CHEAPEST_INSERTION 144.28 млн, CHRISTOFIDES 149.27 млн,
# SAVINGS 149.27 млн. Разрыв с SAVINGS — ровно одна заявка: на Востоке новый
# старт одну теряет, на Юго-востоке добирает две. Размен честный только по
# нашей же шкале, где заявка стоит как 5000 км: 186 заявок за 450 км против
# 185 за 432 км.
#
# Разный старт по районам мы не делаем сознательно: на трёх выгрузках это
# была бы подгонка под данные, а не настройка алгоритма. Перебор
# воспроизводится: `python3 scripts/benchmark.py --heuristics`.
FIRST_SOLUTION_NAME = "LOCAL_CHEAPEST_INSERTION"
FIRST_SOLUTION = getattr(routing_enums_pb2.FirstSolutionStrategy,
                         FIRST_SOLUTION_NAME)
METAHEURISTIC = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH


@dataclass
class _Model:
    manager: pywrapcp.RoutingIndexManager
    routing: pywrapcp.RoutingModel
    order_nodes: list[int]


def _status_name(code: int) -> str:
    """Имя статуса решателя по его номеру.

    Номера в OR-Tools между версиями сдвигались, поэтому имена берём у самой
    библиотеки: зашитая таблица показывала бы «решение не найдено» там, где
    план на самом деле построен.
    """
    for value in _STATUS_VALUES:
        if value.number == code:
            return value.name
    return str(code)


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
        return dist_m[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]

    dist_cb_idx = routing.RegisterTransitCallback(distance_cb)

    # --- время в пути зависит от транспорта, поэтому колбэк свой на каждого ---
    time_cb_indices = []
    for vehicle_id, engineer in enumerate(engineers):
        def make_cb(eng: Engineer):
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
        vehicle_id = next((v for v, e in enumerate(engineers) if e.id == engineer_id), None)
        if vehicle_id is None:
            continue
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

    # --- извлечение маршрутов и пересчёт времён общим кодом ---
    routes: list[Route] = []
    for vehicle_id, engineer in enumerate(engineers):
        sequence: list[Order] = []
        index = routing.Start(vehicle_id)
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if node < n_orders:
                sequence.append(orders[node])
            index = solution.Value(routing.NextVar(index))
        route, _ = evaluate_sequence(engineer, sequence)
        while route is None and sequence:
            # Страховка: если пересчёт всё же не сошёлся с моделью, отдаём
            # столько заявок, сколько помещается, а не теряем весь маршрут.
            sequence = sequence[:-1]
            route, _ = evaluate_sequence(engineer, sequence)
        routes.append(route if route is not None else Route(engineer_id=engineer.id))

    plan = Plan(routes=routes, strategy="optimized",
                solver_status=status_name, solve_seconds=elapsed)
    return _finalize(plan, orders, engineers)
