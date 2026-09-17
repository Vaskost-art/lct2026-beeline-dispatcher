"""Восстановление исполнителей по колонке «Бригада» контрольной выгрузки.

В данных исполнителей как таковых нет: есть отметка, какая бригада выполнила
заявку. Навыки, транспорт, смена и стартовая точка выводятся из того, что
бригада реально делала за день.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from dispatcher.domain import Engineer, shifts
from dispatcher.domain.distance import haversine_km

#: Позже этого времени смена не начинается, даже если окно заявки круглосуточное.
LAST_WINDOW_END = 22 * 60


@dataclass
class CrewFacts:
    """Что бригада реально делала за день, собранное по строкам выгрузки."""

    skills: set[str] = field(default_factory=set)
    districts: set[str] = field(default_factory=set)
    points: list[tuple[float, float]] = field(default_factory=list)
    windows: list[tuple[int, int]] = field(default_factory=list)
    needs_car: bool = False


def build_engineers(crews: dict[str, CrewFacts]) -> list[Engineer]:
    """Восстанавливает профили исполнителей из контрольного распределения."""
    engineers: list[Engineer] = []
    for name in sorted(crews):
        facts = crews[name]
        base_lat = sum(p[0] for p in facts.points) / len(facts.points)
        base_lon = sum(p[1] for p in facts.points) / len(facts.points)

        # разлёт = максимальное удаление точки от базы
        spread = max(haversine_km(base_lat, base_lon, p[0], p[1]) for p in facts.points)
        central = any(d in shifts.CENTRAL_DISTRICTS for d in facts.districts)
        vehicle = shifts.vehicle_for_spread(spread, facts.needs_car, central)

        first = min(w[0] for w in facts.windows)
        last = min(max(w[1] for w in facts.windows), LAST_WINDOW_END)
        shift_start, shift_end = shifts.shift_bounds(first, last)

        engineers.append(Engineer(
            id=name,
            name=name,
            lat=round(base_lat, 6),
            lon=round(base_lon, 6),
            start_address=f"База участка: {', '.join(sorted(facts.districts)[:2])}",
            shift_start=shift_start,
            shift_end=shift_end,
            skills=sorted(facts.skills),
            vehicle=vehicle,
            break_min=shifts.break_minutes(shift_start, shift_end),
        ))
    return engineers
