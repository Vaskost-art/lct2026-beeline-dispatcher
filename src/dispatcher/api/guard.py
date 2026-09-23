"""Сколько расчётов идёт одновременно.

Один расчёт занимает ядро процессора до нескольких минут. Без предела
несколько запросов подряд занимали все ядра и пул потоков, и сервис переставал
отвечать даже на открытие страницы. Диспетчер один, двух мест хватает с
запасом; третий запрос сразу получает понятный ответ, а не висит.
"""
from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from dispatcher.api.envelope import ApiError

#: Одновременных расчётов.
SOLVER_SLOTS = 2

#: Сколько ждать свободного места, прежде чем ответить «занято», секунд.
WAIT_SEC = 5

_slots = threading.BoundedSemaphore(SOLVER_SLOTS)


@contextmanager
def solver_slot() -> Iterator[None]:
    """Занимает место под расчёт на время блока или отвечает 503."""
    if not _slots.acquire(timeout=WAIT_SEC):
        raise ApiError("busy", "Сервис занят другим расчётом: повторите через "
                               "минуту", status=503)
    try:
        yield
    finally:
        _slots.release()
