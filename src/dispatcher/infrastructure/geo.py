"""Геокодирование адресов и расчёт расстояний.

Схема двухуровневая и работает офлайн:

1. `data/geo_cache.json` — кэш точных координат (адрес -> lat/lon). Заполняется
   один раз скриптом `scripts/geocode.py` через OpenStreetMap/Nominatim и
   коммитится в репозиторий. Демонстрация после этого не зависит от сети.
2. Если адреса в кэше нет — координата собирается из центроида района
   (справочник ниже) плюс детерминированное смещение по хэшу адреса.
   Точка помечается как приблизительная, интерфейс показывает это явно.

Второй уровень нужен, чтобы прототип запускался и считал метрики на любой
машине без интернета: ни один адрес не выпадает из плана из-за геокодера.
"""
from __future__ import annotations

import hashlib
import json
import math
import os

from dispatcher.domain.distance import (
    KM_PER_DEG_LAT,
    haversine_km,
    normalize_address,
    normalize_district,
)

PRECISION_EXACT = "exact"              # из кэша, реальный геокодер
PRECISION_APPROX = "approx_district"   # центроид района + смещение

# Дальше этого от центра своего района адрес быть не может: столько не бывает
# даже у подмосковных районов выгрузки, а «улица того же названия в соседнем
# городе» отстоит на десятки километров.
MAX_DISTRICT_RADIUS_KM = 15.0

# Центроиды районов и городов, встречающихся в выгрузках (WGS84).
DISTRICT_CENTROIDS = {
    "Академический": (55.6870, 37.5730),
    "Басманный": (55.7650, 37.6700),
    "Бирюлево Восточное": (55.5920, 37.6600),
    "Бирюлево Западное": (55.5870, 37.6270),
    "Братеево": (55.6350, 37.7560),
    "Выхино": (55.7130, 37.8180),
    "Гагаринский": (55.6880, 37.5650),
    "Даниловский": (55.7100, 37.6200),
    "Домодедово": (55.4400, 37.7600),
    "Донской": (55.7030, 37.6060),
    "Замоскворечье": (55.7350, 37.6320),
    "Зюзино": (55.6560, 37.5760),
    "Зябликово": (55.6120, 37.7470),
    "Кашира": (54.8400, 38.1600),
    "Котловка": (55.6720, 37.5980),
    "Кузьминки": (55.7000, 37.7800),
    "Лефортово": (55.7570, 37.7000),
    "Москворечье - Сабурово": (55.6470, 37.6720),
    "Нагатино - Садовники": (55.6790, 37.6510),
    "Нагатинский Затон": (55.6830, 37.6870),
    "Нагорный": (55.6660, 37.6180),
    "Нижегородский": (55.7320, 37.7360),
    "Орехово Борисово Северное": (55.6180, 37.7120),
    "Орехово Борисово Южное": (55.6070, 37.7250),
    "Рязанский": (55.7190, 37.7920),
    "Ступино": (54.8900, 38.0800),
    "Таганский": (55.7400, 37.6650),
    "Текстильщики": (55.7050, 37.7370),
    "Хамовники": (55.7300, 37.5800),
    "Царицыно": (55.6180, 37.6680),
    "Южнопортовый": (55.7120, 37.6900),
}
MOSCOW_CENTER = (55.7558, 37.6176)

# Радиус разброса точек внутри района при приблизительном геокодировании, км.
APPROX_SPREAD_KM = 1.2



class Geocoder:
    """Адрес -> координата, с кэшем и офлайн-фоллбэком по району."""

    def __init__(self, cache_path: str):
        self.cache_path = cache_path
        self.cache: dict[str, dict[str, float | str | None]] = {}
        if os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as f:
                self.cache = json.load(f)
        self.stats = {PRECISION_EXACT: 0, PRECISION_APPROX: 0}
        # координаты из кэша, которым мы не поверили
        self.rejected: list[dict[str, str | float]] = []

    def locate(self, address: str, district: str) -> tuple[float, float, str]:
        """Возвращает (lat, lon, точность)."""
        key = normalize_address(address)
        hit = self.cache.get(key)
        if hit and hit.get("lat") is not None:
            lat, lon = float(hit["lat"] or 0.0), float(hit["lon"] or 0.0)
            if self._plausible(lat, lon, district):
                self.stats[PRECISION_EXACT] += 1
                return lat, lon, PRECISION_EXACT
            # Геокодер умеет отдать улицу того же названия в другом городе.
            # Такая точка помечена как точная, но уводит маршрут на десятки
            # километров и меняет профиль бригады, поэтому ей не верим.
            self.rejected.append({"address": key, "lat": lat, "lon": lon,
                                  "district": district})

        lat, lon = self._approximate(key, district)
        self.stats[PRECISION_APPROX] += 1
        return lat, lon, PRECISION_APPROX

    def _plausible(self, lat: float, lon: float, district: str) -> bool:
        """Похожа ли координата на адрес в этом районе.

        Центроиды районов заданы с точностью до пары километров, а сами районы
        невелики, поэтому отклонение в десятки километров означает не
        неточность, а другой населённый пункт.
        """
        center = DISTRICT_CENTROIDS.get(normalize_district(district))
        if center is None:
            return True
        return haversine_km(center[0], center[1], lat, lon) <= MAX_DISTRICT_RADIUS_KM

    def _approximate(self, key: str, district: str) -> tuple[float, float]:
        """Центроид района + детерминированное смещение по хэшу адреса.

        Смещение стабильно между запусками, поэтому план воспроизводим.
        """
        base = DISTRICT_CENTROIDS.get(normalize_district(district), MOSCOW_CENTER)
        digest = hashlib.sha256(key.encode("utf-8")).digest()
        # два независимых числа в [0, 1) из разных частей хэша
        u = int.from_bytes(digest[0:4], "big") / 2 ** 32
        v = int.from_bytes(digest[4:8], "big") / 2 ** 32
        # равномерное распределение по кругу радиуса APPROX_SPREAD_KM
        radius = APPROX_SPREAD_KM * math.sqrt(u)
        angle = 2 * math.pi * v
        dlat = radius * math.cos(angle) / KM_PER_DEG_LAT
        dlon = radius * math.sin(angle) / (KM_PER_DEG_LAT * math.cos(math.radians(base[0])))
        return round(base[0] + dlat, 6), round(base[1] + dlon, 6)

    @property
    def coverage(self) -> float:
        """Доля адресов, разрешённых точным геокодером."""
        total = sum(self.stats.values())
        return self.stats[PRECISION_EXACT] / total if total else 0.0

    def report(self) -> dict[str, object]:
        return {
            "exact": self.stats[PRECISION_EXACT],
            "approx": self.stats[PRECISION_APPROX],
            "coverage": round(self.coverage, 3),
            "cache_path": self.cache_path,
            "cache_size": len(self.cache),
            # координаты, которым не поверили: лежат в кэше как точные, но
            # указывают далеко за пределы своего района
            "rejected": len(self.rejected),
            "rejected_addresses": [r["address"] for r in self.rejected],
        }
