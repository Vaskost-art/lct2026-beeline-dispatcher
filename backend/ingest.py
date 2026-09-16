"""Загрузка исходных выгрузок FSM и сборка сценария планирования.

В архиве по каждому району две выгрузки: «Синтетические данные» (вход) и
«Контрольное распределение» (то же самое плюс колонки «Бригада» и «Статус BK»).
Построчно они совпадают, поэтому читаем контрольную: она содержит и вход,
и факт — реальное распределение живого диспетчера, с которым мы сравниваем план.

Из неё собираются:
  * заявки   — координаты, окно, длительность, навык, приоритет, транспорт;
  * инженеры — состав восстанавливается по колонке «Бригада»: навыки из
    фактически выполненных работ, база — центр тяжести точек, смена — из
    диапазона окон, транспорт — из географического разлёта (см. norms.py).
"""
from __future__ import annotations

import csv
import io
import os
from dataclasses import dataclass, field

import norms
from domain import Engineer, Order, parse_hhmm
from geo import Geocoder, haversine_km, normalize_district

RAW_ENCODING = "cp1251"
CSV_DELIMITER = ";"

REGIONS = {
    "vostok": "Восток",
    "yugo_vostok": "Юго-восток",
    "yugocentr": "Югоцентр",
}

STATUS_CANCELLED = "Отменена"


def _parse_dt(value: str) -> int | None:
    """'17.08.2026 20:00' -> минуты от полуночи. None, если поле пустое."""
    value = value.strip()
    if not value:
        return None
    parts = value.split()
    if len(parts) != 2:
        return None
    try:
        return parse_hhmm(parts[1])
    except ValueError:
        return None


def _clean_address(raw: str) -> str:
    """Убирает дубль «г.Город Москва» и номер квартиры для отображения."""
    addr = raw.strip()
    addr = addr.replace("г.Город Москва", "Москва").replace("Город Москва", "Москва")
    return addr.strip(" ,")


@dataclass
class Scenario:
    """Один район на один рабочий день — готовый вход для планировщика."""

    region_key: str
    region_name: str
    orders: list[Order] = field(default_factory=list)
    engineers: list[Engineer] = field(default_factory=list)
    cancelled_ids: list[str] = field(default_factory=list)
    geo_report: dict = field(default_factory=dict)
    duplicate_ids: list[str] = field(default_factory=list)
    # строки выгрузки, которые не удалось разобрать: их нет в плане, и знать
    # об этом должен диспетчер, а не только автор кода
    skipped_rows: list[dict] = field(default_factory=list)

    @property
    def order_by_id(self) -> dict[str, Order]:
        return {o.id: o for o in self.orders}

    @property
    def engineer_by_id(self) -> dict[str, Engineer]:
        return {e.id: e for e in self.engineers}

    def summary(self) -> dict:
        skills = {s: 0 for s in norms.SKILL_BY_TYPE_BK.values()}
        for o in self.orders:
            skills[o.required_skill] = skills.get(o.required_skill, 0) + 1
        vehicles: dict[str, int] = {}
        for e in self.engineers:
            vehicles[e.vehicle] = vehicles.get(e.vehicle, 0) + 1
        return {
            "region_key": self.region_key,
            "region_name": self.region_name,
            "orders": len(self.orders),
            "engineers": len(self.engineers),
            "urgent": sum(1 for o in self.orders if o.priority == norms.PRIORITY_URGENT),
            "with_vehicle_requirement": sum(1 for o in self.orders if o.required_vehicle),
            "cancelled_in_fact": len(self.cancelled_ids),
            "orders_by_skill": skills,
            "engineers_by_vehicle": vehicles,
            "total_work_hours": round(sum(o.duration_min for o in self.orders) / 60, 1),
            "geocoding": self.geo_report,
            "duplicate_ids": self.duplicate_ids,
            "skipped_rows": self.skipped_rows,
        }


def load_scenario(region_key: str, raw_dir: str, cache_path: str) -> Scenario:
    """Читает выгрузку района из каталога с исходными данными."""
    path = os.path.join(raw_dir, f"{region_key}_control.csv")
    with open(path, "rb") as f:
        raw = f.read()
    return parse_control_csv(raw, region_key, cache_path)


def decode_csv(raw: bytes) -> str:
    """Определяет кодировку выгрузки: организаторы отдают cp1251, но файл
    могли пересохранить в UTF-8, в том числе с BOM."""
    for encoding in ("utf-8-sig", RAW_ENCODING, "utf-8"):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        # cp1251 декодирует почти что угодно, поэтому проверяем осмысленность:
        # в шапке обязана быть колонка «Заявка»
        if "Заявка" in text.split("\n", 1)[0]:
            return text
    return raw.decode(RAW_ENCODING, errors="replace")


def _cell(row: dict, name: str) -> str:
    """Значение колонки строкой. В короткой строке CSV недостающие ключи
    приходят как None, поэтому .get(name, "") от падения не спасает."""
    return (row.get(name) or "").strip()


def parse_control_csv(raw: bytes, region_key: str, cache_path: str,
                      region_name: str | None = None) -> Scenario:
    """Разбирает выгрузку в формате организаторов из байтов файла."""
    text = decode_csv(raw)
    rows = [
        r for r in csv.DictReader(io.StringIO(text), delimiter=CSV_DELIMITER)
        if (r.get("Заявка") or "").strip()
    ]

    geocoder = Geocoder(cache_path)
    orders: list[Order] = []
    cancelled: list[str] = []
    # сырые данные по бригадам для последующего восстановления профиля
    crews: dict[str, dict] = {}
    # В выгрузках встречается один и тот же номер заявки в двух строках с
    # разными временными окнами — это два визита по одному адресу. Разводим их
    # в отдельные заявки, иначе одна из них потерялась бы при любом поиске по id.
    seen_ids: dict[str, int] = {}
    duplicates: list[str] = []
    skipped: list[dict] = []

    for row in rows:
        order_id = _cell(row, "Заявка")
        district = _cell(row, "Район")
        address = _clean_address(_cell(row, "Адрес"))
        start = _parse_dt(_cell(row, "Начало"))
        end = _parse_dt(_cell(row, "Окончание"))
        if start is None or end is None:
            # Время не разобрано, в план заявку взять нельзя. Молча потерять
            # её тоже нельзя: план выглядел бы полным, а наряда в нём нет.
            skipped.append({"order_id": order_id,
                            "start": _cell(row, "Начало"),
                            "end": _cell(row, "Окончание")})
            continue

        seen_ids[order_id] = seen_ids.get(order_id, 0) + 1
        if seen_ids[order_id] > 1:
            duplicates.append(order_id)
            order_id = f"{order_id}-{seen_ids[order_id]}"
        if end <= start:                      # окно «0:01–23:59» и прочие сутки
            end = 23 * 60 + 59

        type_bk = _cell(row, "Тип заявки BK")
        type_hd = _cell(row, "Тип заявки HD")
        status_bk = _cell(row, "Статус BK")
        gigabit = _cell(row, "Гигабитное подключение").lower() == "да"
        crew = _cell(row, "Бригада")

        lat, lon, precision = geocoder.locate(address, district)
        order = Order(
            id=order_id,
            lat=lat,
            lon=lon,
            address=address,
            district=normalize_district(district),
            duration_min=norms.duration_for(type_hd, gigabit),
            window_start=start,
            window_end=end,
            priority=norms.priority_for(type_bk, status_bk),
            required_skill=norms.skill_for(type_bk),
            required_vehicle=norms.required_vehicle_for(type_hd, gigabit),
            type_bk=type_bk,
            type_hd=type_hd,
            control_engineer=crew or None,
            geocode_precision=precision,
        )
        orders.append(order)

        if status_bk == STATUS_CANCELLED:
            cancelled.append(order_id)

        if crew:
            info = crews.setdefault(crew, {"skills": set(), "points": [], "windows": [],
                                           "needs_car": False, "districts": set()})
            info["skills"].add(order.required_skill)
            info["points"].append((lat, lon))
            info["windows"].append((start, end))
            info["districts"].add(order.district)
            if order.required_vehicle == norms.VEHICLE_CAR:
                info["needs_car"] = True

    engineers = _build_engineers(crews)
    return Scenario(
        region_key=region_key,
        region_name=region_name or REGIONS.get(region_key, region_key),
        orders=orders,
        engineers=engineers,
        cancelled_ids=cancelled,
        geo_report=geocoder.report(),
        duplicate_ids=sorted(set(duplicates)),
        skipped_rows=skipped,
    )


def _build_engineers(crews: dict[str, dict]) -> list[Engineer]:
    """Восстанавливает профили исполнителей из контрольного распределения."""
    engineers: list[Engineer] = []
    for name in sorted(crews):
        info = crews[name]
        points = info["points"]
        base_lat = sum(p[0] for p in points) / len(points)
        base_lon = sum(p[1] for p in points) / len(points)

        # разлёт = максимальное удаление точки от базы
        spread = max(haversine_km(base_lat, base_lon, p[0], p[1]) for p in points)
        central = any(d in norms.CENTRAL_DISTRICTS for d in info["districts"])
        vehicle = norms.vehicle_for_spread(spread, info["needs_car"], central)

        first = min(w[0] for w in info["windows"])
        last = max(w[1] for w in info["windows"])
        # круглосуточное окно не должно растягивать смену на все сутки
        last = min(last, 22 * 60)
        shift_start, shift_end = norms.shift_bounds(first, last)

        engineers.append(Engineer(
            id=name,
            name=name,
            lat=round(base_lat, 6),
            lon=round(base_lon, 6),
            start_address=f"База участка: {', '.join(sorted(info['districts'])[:2])}",
            shift_start=shift_start,
            shift_end=shift_end,
            skills=sorted(info["skills"]),
            vehicle=vehicle,
            break_min=norms.break_minutes(shift_start, shift_end),
        ))
    return engineers


def load_all(raw_dir: str, cache_path: str) -> dict[str, Scenario]:
    return {key: load_scenario(key, raw_dir, cache_path) for key in REGIONS}
