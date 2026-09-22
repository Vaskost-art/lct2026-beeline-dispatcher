"""Как бригада добирается от точки до точки.

Организаторы: «решение, способное учитывать комбинированные способы
перемещения и реалистично рассчитывать маршруты для бригад без автомобиля,
будет представлять дополнительный интерес при оценке».

Бригада без машины редко идёт пешком все пять километров: она доходит до
остановки, ждёт, едет и доходит от остановки. Одна средняя скорость на весь
путь врёт в обе стороны - на коротком плече завышает время (автобус ради
трёхсот метров никто не ждёт), на длинном занижает возможности бригады.

Поэтому путь собирается из плеч, и для пешей бригады сравниваются два
способа: дойти пешком или доехать с пересадкой на транспорт. Выигрывает
тот, который быстрее, - так же, как выбрал бы сам человек.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from dispatcher.domain.catalog import (
    VEHICLE_BIKE,
    VEHICLE_CAR,
    VEHICLE_FOOT,
    VEHICLE_TRANSIT,
)

#: Скорость движения по плечу, км/ч.
#: Автомобиль и велосипед - «от двери до двери» с поправкой на трафик и
#: парковку. Транспорт - скорость самой поездки: подход к остановке и
#: ожидание считаются отдельными плечами, а не размазаны по средней скорости.
WALK_KMH = 4.5
BIKE_KMH = 12.0
CAR_KMH = 22.0
TRANSIT_RIDE_KMH = 20.0

#: Плечо пешком до остановки и от остановки, км (в каждую сторону).
WALK_TO_STOP_KM = 0.4

#: Ожидание транспорта, минут. Средний интервал городского маршрута пополам.
TRANSIT_WAIT_MIN = 6

MODE_WALK = "пешком"
MODE_TRANSIT = "на транспорте"
MODE_BIKE = "на велосипеде"
MODE_CAR = "на машине"


@dataclass(frozen=True)
class Leg:
    """Одно плечо пути: чем и сколько."""

    mode: str
    km: float
    minutes: int


@dataclass(frozen=True)
class Trip:
    """Путь целиком: сколько минут, сколько километров и из чего собран."""

    minutes: int
    km: float
    legs: tuple[Leg, ...]

    @property
    def combined(self) -> bool:
        """Пеший подход плюс поездка: то самое комбинированное перемещение."""
        return len({leg.mode for leg in self.legs}) > 1

    @property
    def text(self) -> str:
        """«25 мин: 12 пешком и 13 на транспорте» - развёрнуто, для карточки."""
        if not self.legs:
            return "0 мин"
        if not self.combined:
            return f"{self.minutes} мин {self.legs[0].mode}"
        walk = sum(leg.minutes for leg in self.legs if leg.mode == MODE_WALK)
        ride = self.minutes - walk
        return f"{self.minutes} мин: {walk} пешком и {ride} на транспорте"

    @property
    def mode_text(self) -> str:
        """«пешком и транспорт» - коротко, для строки маршрута.

        В списке маршрута на счету каждый пиксель: развёрнутая подпись
        сжимала строку и выдавливала метку приоритета за край.
        """
        if not self.legs:
            return ""
        if not self.combined:
            return self.legs[0].mode
        return "пешком и транспорт"


def _minutes(km: float, speed_kmh: float) -> int:
    return int(math.ceil(km / speed_kmh * 60)) if km > 0 else 0


def _single(km: float, mode: str, speed_kmh: float) -> Trip:
    minutes = _minutes(km, speed_kmh)
    return Trip(minutes=minutes, km=km, legs=(Leg(mode, km, minutes),))


def _with_transit(km: float) -> Trip:
    """Дойти до остановки, доехать, дойти от остановки."""
    approach = min(WALK_TO_STOP_KM, km / 2)
    ride_km = max(0.0, km - approach * 2)
    walk_min = _minutes(approach, WALK_KMH)
    ride_min = _minutes(ride_km, TRANSIT_RIDE_KMH) + TRANSIT_WAIT_MIN
    legs = (Leg(MODE_WALK, approach, walk_min),
            Leg(MODE_TRANSIT, ride_km, ride_min),
            Leg(MODE_WALK, approach, walk_min))
    return Trip(minutes=walk_min * 2 + ride_min, km=km, legs=legs)


def plan_trip(km: float, vehicle: str) -> Trip:
    """Как бригада проедет это расстояние и сколько это займёт.

    Пешая бригада выбирает быстрейший из двух способов: дойти или доехать.
    Бригада на общественном транспорте считается по той же схеме - у неё нет
    другого способа, но пешком она тоже может дойти, если это ближе.
    """
    if km <= 0:
        return Trip(minutes=0, km=0.0, legs=())
    if vehicle == VEHICLE_CAR:
        return _single(km, MODE_CAR, CAR_KMH)
    if vehicle == VEHICLE_BIKE:
        return _single(km, MODE_BIKE, BIKE_KMH)
    if vehicle not in (VEHICLE_FOOT, VEHICLE_TRANSIT):
        return _single(km, MODE_CAR, CAR_KMH)

    on_foot = _single(km, MODE_WALK, WALK_KMH)
    combined = _with_transit(km)
    return combined if combined.minutes < on_foot.minutes else on_foot
