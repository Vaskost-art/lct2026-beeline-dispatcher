"""Расчёт расстояния и времени в пути.

Это доменное правило, а не работа с внешним миром: одни и те же функции зовут
и построитель маршрута, и решатель, и проверка плана. Пока расчёт лежал в
одном файле с геокодером, каждый сервис зависел от инфраструктуры.

Расстояние по дорогам оценивается расстоянием по прямой с коэффициентом
извилистости: допущение объявлено на экране и в документации.
"""
from __future__ import annotations

import math
import re

from dispatcher.domain.norms import DETOUR_FACTOR
from dispatcher.domain.travel import plan_trip

#: Километров в одном градусе широты. Нужна и для расстояний, и для
#: смещения приблизительной точки внутри района.
KM_PER_DEG_LAT = 111.19


def normalize_district(district: str) -> str:
    """«GPON Даниловский» -> «Даниловский»; выравнивает тире и пробелы."""
    name = re.sub(r"^\s*(GPON|FTTB|FMC)\s+", "", district.strip(), flags=re.I)
    name = re.sub(r"\s*[-–—]\s*", " - ", name)
    return re.sub(r"\s+", " ", name).strip()


def normalize_address(address: str) -> str:
    """Ключ кэша: без номера квартиры, схлопнутые пробелы, нижний регистр."""
    addr = re.sub(r",\s*кв\.?\s*\d+.*$", "", address.strip(), flags=re.I)
    addr = re.sub(r"\s+", " ", addr)
    return addr.strip(" ,.").lower()


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Расстояние по прямой между двумя точками, км."""
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def road_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Расстояние по улично-дорожной сети (оценка), км."""
    return haversine_km(lat1, lon1, lat2, lon2) * DETOUR_FACTOR


def travel_minutes(km: float, vehicle: str) -> int:
    """Время в пути, минуты.

    Способ перемещения подбирает `travel.plan_trip`: бригада без машины
    может дойти пешком, а может доехать с пересадкой - считается тот
    вариант, который быстрее.
    """
    return plan_trip(km, vehicle).minutes
