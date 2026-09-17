"""Результат планирования: визит, маршрут, отказ, план целиком."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from dispatcher.domain.clock import hhmm


@dataclass
class Stop:
    """Один визит в маршруте исполнителя."""

    order_id: str
    arrival: int               # план прибытия, минуты
    start: int                 # план начала работ, минуты
    end: int                   # план окончания, минуты
    travel_min: int            # время в пути до этой точки
    travel_km: float           # пробег до этой точки
    wait_min: int              # ожидание открытия временного окна

    def to_dict(self) -> dict[str, object]:
        d = asdict(self)
        for k in ("arrival", "start", "end"):
            d[k] = hhmm(getattr(self, k))
        d["travel_km"] = round(self.travel_km, 2)
        return d


@dataclass
class Route:
    """Маршрут одного исполнителя на день."""

    engineer_id: str
    stops: list[Stop] = field(default_factory=list)

    @property
    def total_km(self) -> float:
        return sum(s.travel_km for s in self.stops)

    @property
    def total_travel_min(self) -> int:
        return sum(s.travel_min for s in self.stops)

    @property
    def total_work_min(self) -> int:
        return sum(s.end - s.start for s in self.stops)

    @property
    def is_used(self) -> bool:
        return bool(self.stops)

    def to_dict(self) -> dict[str, object]:
        return {
            "engineer_id": self.engineer_id,
            "stops": [s.to_dict() for s in self.stops],
            "total_km": round(self.total_km, 2),
            "total_travel_min": self.total_travel_min,
            "total_work_min": self.total_work_min,
        }


@dataclass
class Unassigned:
    """Неназначенная заявка с причиной, понятной диспетчеру (ТЗ п. 2.2)."""

    order_id: str
    reason: str                # короткий машинный код
    reason_text: str           # формулировка для диспетчера

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class Plan:
    """Результат планирования."""

    routes: list[Route] = field(default_factory=list)
    unassigned: list[Unassigned] = field(default_factory=list)
    strategy: str = ""         # 'baseline' | 'optimized'
    solver_status: str = ""
    solve_seconds: float = 0.0

    @property
    def used_engineers(self) -> int:
        """Метрика ТЗ: число уникальных исполнителей хотя бы с одной заявкой."""
        return sum(1 for r in self.routes if r.is_used)

    @property
    def total_km(self) -> float:
        """Метрика ТЗ: суммарный пробег по плану."""
        return sum(r.total_km for r in self.routes)

    @property
    def assigned_count(self) -> int:
        return sum(len(r.stops) for r in self.routes)

    def engineer_of(self, order_id: str) -> str | None:
        for route in self.routes:
            for stop in route.stops:
                if stop.order_id == order_id:
                    return route.engineer_id
        return None

    def stop_of(self, order_id: str) -> tuple[str, int, Stop] | None:
        """Возвращает (engineer_id, позиция в маршруте, Stop)."""
        for route in self.routes:
            for idx, stop in enumerate(route.stops):
                if stop.order_id == order_id:
                    return route.engineer_id, idx, stop
        return None
