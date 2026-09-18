"""Общий доступ к рабочему дню для всех ручек."""
from __future__ import annotations

from dispatcher.api.envelope import ApiError
from dispatcher.api.state import DayState, DayStore, DayVersion
from dispatcher.domain.scenario import Scenario

STORE = DayStore({})


def scenario_of(region: str) -> Scenario:
    scenario = STORE.scenario(region)
    if scenario is None:
        raise ApiError("region_not_found", f"Район «{region}» не найден", 404)
    return scenario


def version_of(region: str) -> DayVersion:
    version = STORE.current(region)
    if version is None:
        raise ApiError("plan_not_built",
                       "План ещё не построен: сначала запустите планирование", 409)
    return version


def undo_labels(region: str) -> list[str]:
    day = STORE.day(region)
    return day.undo_labels if day else []


def day(region: str) -> DayState:
    day = STORE.day(region)
    if day is None:
        raise ApiError("region_not_found", f"Район «{region}» не найден", 404)
    return day
