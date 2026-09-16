"""Планировщик: базовый вариант из ТЗ и оптимизатор на OR-Tools.

Базовый вариант (ТЗ п. 2.3) задан дословно: заявки обрабатываются по порядку
поступления и назначаются первому по порядку во входных данных доступному
инженеру, удовлетворяющему обязательным ограничениям; порядок посещения
совпадает с порядком назначения; глобальная оптимизация не выполняется.
Он нужен как честная точка отсчёта для сравнения метрик.

Оптимизатор решает VRPTW с ограничениями по навыку, транспорту и смене.
Приоритеты целевой функции, сверху вниз:
  1. назначить как можно больше заявок (срочные — с повышенным весом);
  2. задействовать как можно меньше исполнителей  } обе метрики ТЗ,
  3. проехать как можно меньше километров.        } персонал важнее пробега
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

_STATUS_VALUES = [
    value
    for enum_type in routing_enums_pb2.RoutingSearchStatus.DESCRIPTOR.enum_types
    for value in enum_type.values
]

import norms
from domain import Engineer, Order, Plan, Route, Unassigned
from geo import road_km, travel_minutes
from routing import evaluate_sequence, insertion_cost

# --- веса целевой функции (в «метрах», единица внутренней стоимости) ---------
DROP_PENALTY_NORMAL = 5_000_000      # не назначить обычную заявку
DROP_PENALTY_URGENT = 20_000_000     # не назначить срочную — вчетверо дороже
ENGINEER_FIXED_COST = 120_000        # вывод ещё одного исполнителя ≈ 120 км пробега

DEFAULT_TIME_LIMIT_SEC = 15


# --- причины неназначения, понятные диспетчеру (ТЗ п. 2.2) -------------------
REASON_TEXT = {
    "no_skill": "Ни у одного исполнителя нет требуемого навыка «{skill}».",
    "no_vehicle": "Требуется транспорт «{vehicle}», но исполнителей с таким "
                  "транспортом нет или у них нет нужного навыка.",
    "window_unreachable": "Ни один подходящий исполнитель не успевает доехать "
                          "во временное окно {window}: смена заканчивается раньше "
                          "или дорога занимает больше времени, чем есть до конца окна.",
    "shift_overflow": "Работа длительностью {duration} мин не помещается в смену "
                      "ни у одного подходящего исполнителя.",
    "no_capacity": "Все подходящие исполнители в окне {window} уже заняты "
                   "другими заявками.",
}


def _reason(code: str, order: Order) -> Unassigned:
    text = REASON_TEXT[code].format(
        skill=order.required_skill,
        vehicle=order.required_vehicle or "—",
        window=order.window_text,
        duration=order.duration_min,
    )
    return Unassigned(order_id=order.id, reason=code, reason_text=text)


def diagnose(order: Order, engineers: list[Engineer]) -> Unassigned:
    """Определяет, почему заявку не удалось назначить.

    Проверки идут от самых жёстких ограничений к самым мягким, поэтому
    диспетчер получает первопричину, а не следствие.
    """
    by_skill = [e for e in engineers if order.required_skill in e.skills]
    if not by_skill:
        return _reason("no_skill", order)

    by_resource = [e for e in by_skill
                   if not order.required_vehicle or e.vehicle == order.required_vehicle]
    if not by_resource:
        return _reason("no_vehicle", order)

    # существует ли исполнитель, который вообще способен выполнить заявку,
    # если бы ехал к ней прямо с базы и был свободен весь день
    reachable = False
    fits_shift = False
    for e in by_resource:
        km = road_km(e.lat, e.lon, order.lat, order.lon)
        arrival = e.shift_start + travel_minutes(km, e.vehicle)
        start = max(arrival, order.window_start)
        if start <= order.window_end:
            reachable = True
            # work_end: заявка, не влезающая именно из-за обеда, иначе
            # получит причину «все исполнители заняты» при пустом маршруте
            if start + order.duration_min <= e.work_end:
                fits_shift = True
                break

    if not reachable:
        return _reason("window_unreachable", order)
    if not fits_shift:
        return _reason("shift_overflow", order)
    return _reason("no_capacity", order)


def _finalize(plan: Plan, orders: list[Order], engineers: list[Engineer]) -> Plan:
    """Заполняет причины по всем заявкам, не попавшим в маршруты."""
    assigned = {s.order_id for r in plan.routes for s in r.stops}
    by_id = {o.id: o for o in orders}
    plan.unassigned = [diagnose(by_id[oid], engineers)
                       for oid in (o.id for o in orders) if oid not in assigned]
    return plan


# --- базовый вариант ---------------------------------------------------------

def solve_baseline(orders: list[Order], engineers: list[Engineer],
                   locked: dict[str, str] | None = None) -> Plan:
    """Последовательное распределение «как есть» — точка отсчёта из ТЗ."""
    started = time.perf_counter()
    locked = locked or {}
    routes = {e.id: Route(engineer_id=e.id) for e in engineers}
    sequences: dict[str, list[Order]] = {e.id: [] for e in engineers}

    for order in orders:                      # по порядку поступления
        pinned = locked.get(order.id)
        for engineer in engineers:            # первый подходящий по порядку
            if pinned is not None and engineer.id != pinned:
                continue
            if not engineer.can_do(order):
                continue
            candidate = sequences[engineer.id] + [order]
            route, _ = evaluate_sequence(engineer, candidate)
            if route is not None:
                sequences[engineer.id] = candidate
                routes[engineer.id] = route
                break

    plan = Plan(routes=list(routes.values()), strategy="baseline",
                solver_status="SEQUENTIAL",
                solve_seconds=round(time.perf_counter() - started, 3))
    return _finalize(plan, orders, engineers)


# --- оптимизатор -------------------------------------------------------------

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
            if i == j or i == end_node or j == end_node:
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
        penalty = (DROP_PENALTY_URGENT if order.priority == norms.PRIORITY_URGENT
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


# --- жадная эвристика («честный» промежуточный вариант) ----------------------

def solve_greedy(orders: list[Order], engineers: list[Engineer],
                 locked: dict[str, str] | None = None) -> Plan:
    """Жадное распределение с лучшей вставкой.

    Нужна как вторая точка отсчёта: базовый вариант из ТЗ намеренно наивен,
    и сравнивать оптимизатор только с ним было бы некорректно. Здесь заявки
    идут от срочных и ранних окон к поздним, каждая ставится в ту позицию
    маршрута, которая даёт минимальный прирост пробега, и предпочтение
    отдаётся уже задействованным исполнителям — чтобы не раздувать персонал.
    """
    started = time.perf_counter()
    locked = locked or {}
    by_id = {o.id: o for o in orders}
    routes = {e.id: Route(engineer_id=e.id) for e in engineers}
    engineer_by_id = {e.id: e for e in engineers}

    queue = sorted(
        orders,
        key=lambda o: (0 if o.priority == norms.PRIORITY_URGENT else 1,
                       o.window_start, o.window_end, -o.duration_min),
    )

    for order in queue:
        best: tuple[float, str, Route] | None = None
        pinned = locked.get(order.id)
        for engineer in engineers:
            if pinned is not None and engineer.id != pinned:
                continue
            if not engineer.can_do(order):
                continue
            route = routes[engineer.id]
            for position in range(len(route.stops) + 1):
                ok, delta, new_route = insertion_cost(
                    engineer, route, by_id, order, position)
                if not ok:
                    continue
                # штраф за вывод нового исполнителя — метрика «персонал» важнее пробега
                score = delta + (ENGINEER_FIXED_COST / 1000.0 if not route.is_used else 0.0)
                if best is None or score < best[0]:
                    best = (score, engineer.id, new_route)
        if best is not None:
            routes[best[1]] = best[2]

    plan = Plan(routes=list(routes.values()), strategy="greedy",
                solver_status="GREEDY_INSERTION",
                solve_seconds=round(time.perf_counter() - started, 3))
    return _finalize(plan, orders, engineers)


STRATEGIES = {
    "baseline": solve_baseline,
    "greedy": solve_greedy,
    "optimized": solve_optimized,
}

# Название на рабочем экране — тем языком, которым думает диспетчер.
# Точная формулировка нужна только там, где варианты сравниваются между собой.
STRATEGY_TITLES = {
    "baseline": "Без оптимизации",
    "greedy": "Быстрый расчёт",
    "optimized": "Оптимальный план",
}

STRATEGY_FULL_TITLES = {
    "baseline": "Без оптимизации (базовый вариант по ТЗ)",
    "greedy": "Быстрый расчёт (жадная эвристика)",
    "optimized": "Оптимальный план (OR-Tools)",
}

STRATEGY_HINTS = {
    "baseline": "Заявки раздаются по порядку поступления первому свободному "
                "исполнителю. Так работает распределение без планировщика.",
    "greedy": "Доли секунды. Срочные и ранние окна первыми, каждая заявка "
              "встаёт туда, где меньше всего добавляет пробега.",
    "optimized": "Перебирает варианты заданное число секунд и ищет план, "
                 "который закроет больше заявок меньшим числом людей.",
}


# --- статус расчёта человеческим языком (показываем рядом с планом) ----------
# Диспетчеру важно знать не код решателя, а одно: можно ли доверять плану
# и имеет ли смысл дать расчёту больше времени.

_STATUS_TEXT = {
    "SEQUENTIAL": ("Заявки разошлись по порядку поступления — без оптимизации.",
                   "neutral"),
    "GREEDY_INSERTION": ("Быстрая эвристика: план построен за доли секунды, "
                         "оптимальность не гарантируется.", "neutral"),
    "MANUAL_REASSIGN": ("План изменён вручную диспетчером.", "neutral"),
    "ROUTING_SUCCESS": ("Решение найдено. Это лучший вариант, который "
                        "успел проверить планировщик за отведённое время — "
                        "больше секунд может дать чуть короче маршруты.", "ok"),
    "ROUTING_NOT_SOLVED": ("Планировщик не успел построить ни одного варианта. "
                           "Увеличьте время расчёта.", "bad"),
    "ROUTING_FAIL": ("Решение не найдено: при заданных ограничениях плана "
                     "не существует.", "bad"),
    "ROUTING_FAIL_TIMEOUT": ("Время расчёта вышло раньше, чем нашёлся первый "
                             "вариант. Увеличьте время расчёта.", "bad"),
    "ROUTING_INVALID": ("Модель некорректна — это ошибка сервиса, "
                        "а не данных.", "bad"),
    "ROUTING_PARTIAL_SUCCESS_LOCAL_OPTIMUM_NOT_REACHED": (
        "Решение найдено, но время вышло раньше, чем поиск дошёл до локального "
        "оптимума — больше секунд может дать чуть короче маршруты.", "ok"),
    "ROUTING_OPTIMAL": ("Решение найдено и доказано оптимальным при заданных "
                        "ограничениях.", "ok"),
    "ROUTING_INFEASIBLE": ("При заданных ограничениях плана не существует.",
                           "bad"),
    "EMPTY": ("Планировать нечего: нет заявок или нет исполнителей.", "neutral"),
}

# Хвост, который навешивает перепланирование, когда пришлось отпустить
# уже начатые работы.
_NO_FREEZE = "_NO_FREEZE_FALLBACK"


def status_text(solver_status: str) -> dict:
    """Код статуса решателя -> текст и уровень для интерфейса."""
    code = solver_status or ""
    fallback = code.endswith(_NO_FREEZE)
    if fallback:
        code = code[: -len(_NO_FREEZE)]

    text, level = _STATUS_TEXT.get(
        code, (f"Статус планировщика: {code or 'неизвестен'}.", "neutral"))
    if fallback:
        text += (" Сохранить уже начатые работы на прежних местах не удалось — "
                 "маршруты пересобраны с нуля, сверьте их с бригадами.")
        level = "warn"
    return {"code": solver_status, "text": text, "level": level}
