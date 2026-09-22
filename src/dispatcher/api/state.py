"""Хранилище рабочих дней за узким интерфейсом.

Ручки не трогают хранилище напрямую: они просят состояние участка, кладут
новую версию плана и делают шаг назад. Благодаря этому реализация хранения
меняется в одном месте, а не в двадцати двух ручках.

Версии дублируются в журнал (базу), если он передан: перезапуск сервиса
посреди смены не должен стирать работу диспетчера. Сам день и его версии
описаны в `dispatcher.api.day`.
"""
from __future__ import annotations

from copy import deepcopy

from dispatcher.api.day import DayState, DayVersion, PreviewCache
from dispatcher.api.journal import DayJournal
from dispatcher.domain.scenario import Scenario
from dispatcher.services.dataset import (
    DatasetError,
    rebuild,
    snapshot_from_json,
    snapshot_of,
    snapshot_to_json,
)

#: Сколько версий дня держим. Глубже диспетчеру не нужно, а каждая версия
#: хранит полную копию плана.
HISTORY_LIMIT = 20

__all__ = ["DayState", "DayStore", "DayVersion", "HISTORY_LIMIT", "PreviewCache"]


class DayStore:
    """Хранилище рабочих дней по участкам."""

    def __init__(self, scenarios: dict[str, Scenario],
                 journal: DayJournal | None = None) -> None:
        self._journal = journal
        self._days = {key: DayState(scenario=value)
                      for key, value in scenarios.items()}

    def reset(self, scenarios: dict[str, Scenario],
              journal: DayJournal | None = None) -> None:
        """Наполняет хранилище участками, не подменяя сам объект.

        Подмена объекта на старте оставила бы ручки со ссылкой на пустое
        хранилище: они берут его один раз, при импорте.
        """
        if journal is not None:
            self._journal = journal
        self._days = {key: DayState(scenario=value)
                      for key, value in scenarios.items()}
        for key in self._days:
            self._restore(key)

    def _restore(self, region: str) -> int:
        """Поднимает версии дня из журнала. Возвращает, сколько подняли.

        Непрочитанная версия не должна мешать работе: до неё день уже был
        рабочим, и лучше начать со свежего расчёта, чем не открыться вовсе.
        """
        if self._journal is None:
            return 0
        day = self._days.get(region)
        if day is None:
            return 0
        for payload in self._journal.load(region):
            try:
                snapshot = snapshot_from_json(payload)
                plan, metrics, _ = rebuild(snapshot)
            except (DatasetError, KeyError, TypeError, ValueError):
                break
            day.versions.append(DayVersion(
                label=snapshot.label, plan=plan, metrics=metrics,
                orders=snapshot.orders, engineers=snapshot.engineers,
                locked=snapshot.locked, manual=snapshot.manual))
        return len(day.versions)

    def regions(self) -> list[str]:
        return list(self._days)

    def has(self, region: str) -> bool:
        return region in self._days

    def scenario(self, region: str) -> Scenario | None:
        day = self._days.get(region)
        return day.scenario if day else None

    def replace_scenario(self, region: str, scenario: Scenario,
                         events: list[dict[str, object]] | None = None) -> None:
        """Загружен новый набор данных: день участка начинается заново."""
        self._days[region] = DayState(scenario=scenario,
                                      dataset_events=list(events or []))
        if self._journal is not None:
            self._journal.clear(region)

    def day(self, region: str) -> DayState | None:
        return self._days.get(region)

    def current(self, region: str) -> DayVersion | None:
        day = self._days.get(region)
        return day.current if day else None

    def push(self, region: str, version: DayVersion) -> DayVersion:
        """Кладёт новую версию дня.

        Прежняя версия остаётся нетронутой: её копия и есть шаг назад.
        """
        day = self._days.get(region)
        if day is None:
            raise KeyError(region)
        day.versions.append(version)
        if len(day.versions) > HISTORY_LIMIT:
            del day.versions[0]
        if self._journal is not None:
            self._journal.record(region, version.label, snapshot_to_json(
                snapshot_of(day.scenario.region_key, day.scenario.region_name,
                            version.label, version.plan, version.orders,
                            version.engineers, version.locked, version.manual)))
        return version

    def step_back(self, region: str) -> DayVersion | None:
        """Возвращает предыдущую версию дня, снимая последнюю."""
        day = self._days.get(region)
        if day is None or len(day.versions) < 2:
            return None
        day.versions.pop()
        if self._journal is not None:
            self._journal.forget_last(region)
        return day.current

    def snapshot(self, region: str, label: str) -> DayVersion | None:
        """Копия текущей версии под новым именем: основа для правки."""
        current = self.current(region)
        if current is None:
            return None
        return DayVersion(
            label=label,
            plan=deepcopy(current.plan),
            metrics=deepcopy(current.metrics),
            orders=list(current.orders),
            engineers=deepcopy(current.engineers),
            locked=dict(current.locked),
        )
