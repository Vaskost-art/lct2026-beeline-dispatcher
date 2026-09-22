"""Рабочий день участка: версия плана, предпросмотр и история.

Версия плана неизменяема: каждая правка кладёт следующую. Отсюда история дня
и шаг назад, и отсюда же невозможность отдать диспетчеру чужой предпросмотр.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from dispatcher.domain import Engineer, Order, Plan
from dispatcher.domain.scenario import Scenario
from dispatcher.services.replanning.events import ReplanResult


@dataclass
class DayVersion:
    """Одна версия рабочего дня участка."""

    label: str
    plan: Plan
    metrics: dict[str, object]
    orders: list[Order]
    engineers: list[Engineer]
    locked: dict[str, str] = field(default_factory=dict)
    #: Что бригады получили в офисе утром: бригада -> устройство -> сколько.
    #: Выдача идёт один раз, по первому плану дня, и дальше не меняется:
    #: сумку в поле не пополняют. Пусто значит «ещё не выдавали».
    issued: dict[str, dict[str, int]] = field(default_factory=dict)
    #: Решение человека, а не пересчёт. Шаг назад откатывает и то и другое,
    #: но вопрос «что потеряется, если собрать день заново» касается только
    #: ручных правок: пересчёты в этом списке - шум, и после десятка прогонов
    #: подтверждение показывало десять одинаковых строк «Пересчёт».
    manual: bool = False


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

    @property
    def manual_labels(self) -> list[str]:
        """Решения человека, принятые за смену: их отменит сборка заново."""
        return [version.label for version in reversed(self.versions) if version.manual]
