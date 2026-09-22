"""Журнал рабочего дня: версии плана переживают перезапуск сервиса.

Хранилище дня держит версии в памяти процесса - так быстрее и так проще
шаг назад. Журнал дублирует их в базу: перезапуск сервиса посреди смены
перестаёт стирать работу диспетчера.

База - не обязательное условие работы. Если кластер не поднят, сервис
работает как прежде, из памяти, и говорит об этом в `/api/meta`: на защите
сорваться из-за недоступной базы нельзя.
"""
from __future__ import annotations

import logging
from typing import Protocol

from sqlalchemy.exc import SQLAlchemyError

from dispatcher.infrastructure.db.repositories import PlanRepository, RegionRepository
from dispatcher.infrastructure.db.session import session

log = logging.getLogger("dispatcher.journal")

#: Сколько версий поднимаем при старте. Совпадает с глубиной истории в памяти.
RESTORE_LIMIT = 20


class DayJournal(Protocol):
    """Куда хранилище дня кладёт версии, чтобы они пережили перезапуск."""

    def record(self, region: str, label: str, payload: dict[str, object]) -> None:
        """Записывает новую версию дня."""

    def forget_last(self, region: str) -> None:
        """Сворачивает последнюю версию: диспетчер сделал шаг назад."""

    def load(self, region: str) -> list[dict[str, object]]:
        """Версии участка, старые первыми."""

    def clear(self, region: str) -> None:
        """Сворачивает весь день: пришёл новый набор данных."""


class DbJournal:
    """Журнал в PostgreSQL. Отказ базы не останавливает работу."""

    def __init__(self) -> None:
        #: Выключается на первой же ошибке: сыпать в журнал одинаковыми
        #: отказами на каждую правку бессмысленно, а сервис работает и без базы.
        self.available = True

    def record(self, region: str, label: str, payload: dict[str, object]) -> None:
        if not self.available:
            return
        try:
            with session() as active:
                regions = RegionRepository(active)
                stored = regions.by_key(region)
                if stored is None:
                    stored = regions.save(region, str(payload.get("region_name")
                                                      or region), {})
                previous = PlanRepository(active).current(stored.id)
                locked = payload.get("locked")
                PlanRepository(active).add_version(
                    stored.id, payload, label,
                    strategy=str(payload.get("strategy") or ""),
                    solver_status=str(payload.get("solver_status") or ""),
                    locked=locked if isinstance(locked, dict) else {},
                    parent_id=previous.id if previous else None)
                active.commit()
        except SQLAlchemyError as error:
            self._off("записать версию дня", error)

    def forget_last(self, region: str) -> None:
        if not self.available:
            return
        try:
            with session() as active:
                stored = RegionRepository(active).by_key(region)
                if stored is None:
                    return
                PlanRepository(active).drop_last(stored.id)
                active.commit()
        except SQLAlchemyError as error:
            self._off("свернуть версию дня", error)

    def clear(self, region: str) -> None:
        if not self.available:
            return
        try:
            with session() as active:
                stored = RegionRepository(active).by_key(region)
                if stored is None:
                    return
                PlanRepository(active).drop_all(stored.id)
                active.commit()
        except SQLAlchemyError as error:
            self._off("очистить день в базе", error)

    def load(self, region: str) -> list[dict[str, object]]:
        if not self.available:
            return []
        try:
            with session() as active:
                stored = RegionRepository(active).by_key(region)
                if stored is None:
                    return []
                versions = PlanRepository(active).history(stored.id, RESTORE_LIMIT)
                return [version.payload for version in reversed(versions)
                        if isinstance(version.payload, dict)]
        except SQLAlchemyError as error:
            self._off("поднять день из базы", error)
            return []

    def _off(self, what: str, error: Exception) -> None:
        self.available = False
        log.warning("Не удалось %s: %s. Дальше работаем из памяти.", what, error)
