"""Рабочее состояние диспетчера за узким интерфейсом.

Ручки не трогают хранилище напрямую: они просят состояние участка, кладут
новую версию плана и делают шаг назад. Благодаря этому реализация хранения
меняется в одном месте, а не в двадцати двух ручках.

Версия плана неизменяема: каждая правка кладёт следующую. Отсюда история дня
и шаг назад, и отсюда же невозможность отдать диспетчеру чужой предпросмотр.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field

from dispatcher.domain import Engineer, Order, Plan
from dispatcher.domain.scenario import Scenario
from dispatcher.services.replanning.events import ReplanResult

#: Сколько версий дня держим. Глубже диспетчеру не нужно, а каждая версия
#: хранит полную копию плана.
HISTORY_LIMIT = 20


@dataclass
class DayVersion:
    """Одна версия рабочего дня участка."""

    label: str
    plan: Plan
    metrics: dict[str, object]
    orders: list[Order]
    engineers: list[Engineer]
    locked: dict[str, str] = field(default_factory=dict)


@dataclass
class PreviewCache:
    """Посчитанный, но ещё не применённый результат события дня."""

    signature: tuple[object, ...]
    version_number: int
    result: ReplanResult


@dataclass
class DayState:
    """Текущий день участка и его история."""

    scenario: Scenario
    versions: list[DayVersion] = field(default_factory=list)
    dataset_events: list[dict[str, object]] = field(default_factory=list)
    #: Предпросмотр перепланирования: признак события и номер версии, на
    #: которой он посчитан. Привязка к номеру, а не к объекту плана: иначе
    #: диспетчер может получить предпросмотр, посчитанный для другого дня.
    preview: PreviewCache | None = None

    @property
    def current(self) -> DayVersion | None:
        return self.versions[-1] if self.versions else None

    @property
    def undo_labels(self) -> list[str]:
        """Что откатит шаг назад, новое первым."""
        return [version.label for version in reversed(self.versions[:-1])]


class DayStore:
    """Хранилище рабочих дней по участкам."""

    def __init__(self, scenarios: dict[str, Scenario]) -> None:
        self._days = {key: DayState(scenario=value)
                      for key, value in scenarios.items()}

    def reset(self, scenarios: dict[str, Scenario]) -> None:
        """Наполняет хранилище участками, не подменяя сам объект.

        Подмена объекта на старте оставила бы ручки со ссылкой на пустое
        хранилище: они берут его один раз, при импорте.
        """
        self._days = {key: DayState(scenario=value)
                      for key, value in scenarios.items()}

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
        return version

    def step_back(self, region: str) -> DayVersion | None:
        """Возвращает предыдущую версию дня, снимая последнюю."""
        day = self._days.get(region)
        if day is None or len(day.versions) < 2:
            return None
        day.versions.pop()
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
