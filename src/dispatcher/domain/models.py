"""Вход планирования: заявка и исполнитель.

Единицы измерения: время и длительность в минутах, расстояние в
километрах. Наружу время отдаётся строкой ЧЧ:ММ.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from dispatcher.domain.catalog import VEHICLE_CAR
from dispatcher.domain.clock import hhmm


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
    required_vehicle: str | None = None   # None = ограничения нет

    #: Что бригада везёт клиенту: роутер, приставка, колонка. Пустой список
    #: значит, что оборудование не нужно.
    equipment: list[str] = field(default_factory=list)

    # справочная информация из исходных данных (для интерфейса и объяснений)
    type_bk: str = ""
    type_hd: str = ""
    control_engineer: str | None = None   # кто выполнял по факту
    geocode_precision: str = "unknown"       # см. geo.py

    @property
    def window_text(self) -> str:
        return f"{hhmm(self.window_start)}–{hhmm(self.window_end)}"

    def to_dict(self) -> dict[str, object]:
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

    #: Перепланирование в течение дня: сколько первых визитов маршрута уже
    #: начаты и раньше какого момента к остальным не выехать. О новом
    #: задании бригада узнаёт в момент события, а не когда закончила
    #: предыдущий визит: иначе план отправлял её на аварию раньше, чем
    #: авария поступила.
    resume_after: int = 0
    resume_at: int = 0
    #: Заявка, к которой бригада уже едет в момент события: её она знала с
    #: утра, и на неё правило «не раньше события» не распространяется.
    #: Иначе событие у одной бригады сдвигало визиты всех остальных на время
    #: дороги.
    en_route_to: str = ""

    @property
    def work_end(self) -> int:
        """Момент, до которого могут идти работы: конец смены минус перерыв."""
        return max(self.shift_start, self.shift_end - self.break_min)

    @property
    def shift_text(self) -> str:
        base = f"{hhmm(self.shift_start)}–{hhmm(self.shift_end)}"
        return f"{base}, перерыв {self.break_min} мин" if self.break_min else base

    def ready_for(self, position: int, order_id: str, clock: int) -> int:
        """Когда бригада может выехать к визиту номер `position` маршрута.

        После события начатое она доделывает, а к новому заданию выезжает не
        раньше, чем о нём узнала. К заявке, к которой уже едет по прежнему
        плану, - как ехала. Одно правило для построителя маршрута и
        независимой проверки; решатель выражает его в своей модели
        (`services/planning/frozen.py`).
        """
        if position == self.resume_after and order_id != self.en_route_to:
            return max(clock, self.resume_at)
        return clock

    def can_do(self, order: Order) -> bool:
        """Проверка «жёстких» ограничений навыка и ресурса (без времени)."""
        if order.required_skill not in self.skills:
            return False
        return not order.required_vehicle or order.required_vehicle == self.vehicle

    def to_dict(self) -> dict[str, object]:
        d = asdict(self)
        d["shift_start"] = hhmm(self.shift_start)
        d["shift_end"] = hhmm(self.shift_end)
        d["work_end"] = hhmm(self.work_end)
        d["shift_text"] = self.shift_text
        return d


