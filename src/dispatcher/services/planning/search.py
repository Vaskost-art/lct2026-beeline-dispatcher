"""Настройки поиска OR-Tools и имена его состояний.

Решается VRPTW с ограничениями по навыку, транспорту и смене. Приоритеты
целевой функции сверху вниз: больше назначенных заявок, меньше занятых
исполнителей, меньше пробег.
"""
from __future__ import annotations

from dataclasses import dataclass

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

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
