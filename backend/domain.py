"""Доменные сущности планировщика.

Единицы измерения (по ТЗ):
  время        — минуты от 00:00 текущих суток (внутри), HH:MM (наружу)
  длительность — минуты
  расстояние   — километры
  координаты   — широта/долгота (WGS84)
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


# --- Справочники из ТЗ (п. 2.4.1) -------------------------------------------

SKILL_LOCAL = "Локальные работы"
SKILL_CONNECT = "Работы на подключение и дозаказы"
SKILL_EMERGENCY = "Аварийные работы"
SKILLS = (SKILL_LOCAL, SKILL_CONNECT, SKILL_EMERGENCY)

VEHICLE_CAR = "Автомобиль"
VEHICLE_FOOT = "Пешеход"
VEHICLE_BIKE = "Велосипед"
VEHICLE_TRANSIT = "Общественный транспорт"
VEHICLES = (VEHICLE_CAR, VEHICLE_FOOT, VEHICLE_BIKE, VEHICLE_TRANSIT)

PRIORITY_NORMAL = "Обычная"
PRIORITY_URGENT = "Срочная"
PRIORITIES = (PRIORITY_NORMAL, PRIORITY_URGENT)


def hhmm(minutes: int) -> str:
    """Минуты от полуночи -> 'HH:MM'. Поддерживает выход за 24:00."""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def parse_hhmm(text: str) -> int:
    """'ЧЧ:ММ' -> минуты от полуночи.

    Проверяет диапазон: без этого «25:99» разбиралось бы молча и уезжало
    за пределы суток, ломая окна и смены дальше по цепочке.
    """
    parts = str(text).strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"время должно быть в формате ЧЧ:ММ, получено «{text}»")
    hours, minutes = parts
    if not (hours.isdigit() and minutes.isdigit()):
        raise ValueError(f"время должно быть в формате ЧЧ:ММ, получено «{text}»")
    h, m = int(hours), int(minutes)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f"время «{text}» вне суток: часы 00–23, минуты 00–59")
    return h * 60 + m


@dataclass
class Order:
    """Заявка."""

    id: str
    lat: float
    lon: float
    address: str
    district: str
    duration_min: int
    window_start: int          # минуты от полуночи
    window_end: int
    priority: str              # PRIORITIES
    required_skill: str        # SKILLS
    required_vehicle: Optional[str] = None   # None = ограничения нет

    # справочная информация из исходных данных (для интерфейса и объяснений)
    type_bk: str = ""
    type_hd: str = ""
    control_engineer: Optional[str] = None   # кто выполнял по факту
    geocode_precision: str = "unknown"       # см. geo.py

    @property
    def window_text(self) -> str:
        return f"{hhmm(self.window_start)}–{hhmm(self.window_end)}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["window_start"] = hhmm(self.window_start)
        d["window_end"] = hhmm(self.window_end)
        return d


@dataclass
class Engineer:
    """Исполнитель (бригада или техник)."""

    id: str
    name: str
    lat: float                 # стартовая точка
    lon: float
    start_address: str
    shift_start: int           # минуты от полуночи
    shift_end: int
    skills: list[str] = field(default_factory=list)   # от 1 до 3 навыков
    vehicle: str = VEHICLE_CAR

    # Перерыв на обед, минут за смену. Время перерыва не фиксируется: бригада
    # обедает когда получится, но эти минуты вычитаются из ёмкости дня.
    # Жёсткий интервал в модели пробовался и был отвергнут: он заметно ухудшал
    # поиск решателя, не давая взамен ничего, кроме точного времени обеда.
    break_min: int = 0

    @property
    def work_end(self) -> int:
        """Момент, до которого могут идти работы: конец смены минус перерыв."""
        return max(self.shift_start, self.shift_end - self.break_min)

    @property
    def shift_text(self) -> str:
        base = f"{hhmm(self.shift_start)}–{hhmm(self.shift_end)}"
        return f"{base}, перерыв {self.break_min} мин" if self.break_min else base

    def can_do(self, order: Order) -> bool:
        """Проверка «жёстких» ограничений навыка и ресурса (без времени)."""
        if order.required_skill not in self.skills:
            return False
        if order.required_vehicle and order.required_vehicle != self.vehicle:
            return False
        return True

    def to_dict(self) -> dict:
        d = asdict(self)
        d["shift_start"] = hhmm(self.shift_start)
        d["shift_end"] = hhmm(self.shift_end)
        d["work_end"] = hhmm(self.work_end)
        d["shift_text"] = self.shift_text
        return d


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

    def to_dict(self) -> dict:
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

    def to_dict(self) -> dict:
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

    def to_dict(self) -> dict:
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

    def engineer_of(self, order_id: str) -> Optional[str]:
        for route in self.routes:
            for stop in route.stops:
                if stop.order_id == order_id:
                    return route.engineer_id
        return None

    def stop_of(self, order_id: str) -> Optional[tuple[str, int, Stop]]:
        """Возвращает (engineer_id, позиция в маршруте, Stop)."""
        for route in self.routes:
            for idx, stop in enumerate(route.stops):
                if stop.order_id == order_id:
                    return route.engineer_id, idx, stop
        return None
