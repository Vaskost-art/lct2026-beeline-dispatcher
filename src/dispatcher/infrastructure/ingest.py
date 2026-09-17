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

from dispatcher.domain import (
    PRIORITY_URGENT,
    VEHICLE_CAR,
    Engineer,
    Order,
    norms,
)
from dispatcher.domain.distance import normalize_district
from dispatcher.infrastructure.crews import CrewFacts, build_engineers
from dispatcher.infrastructure.csvfile import (
    CSV_DELIMITER,
    _cell,
    _clean_address,
    _parse_dt,
    decode_csv,
)
from dispatcher.infrastructure.geo import Geocoder

REGIONS = {
    "vostok": "Восток",
    "yugo_vostok": "Юго-восток",
    "yugocentr": "Югоцентр",
}

STATUS_CANCELLED = "Отменена"


@dataclass
class Scenario:
    """Один район на один рабочий день — готовый вход для планировщика."""

    region_key: str
    region_name: str
    orders: list[Order] = field(default_factory=list)
    engineers: list[Engineer] = field(default_factory=list)
    cancelled_ids: list[str] = field(default_factory=list)
    geo_report: dict[str, object] = field(default_factory=dict)
    duplicate_ids: list[str] = field(default_factory=list)
    # строки выгрузки, которые не удалось разобрать: их нет в плане, и знать
    # об этом должен диспетчер, а не только автор кода
    skipped_rows: list[dict[str, str]] = field(default_factory=list)

    @property
    def order_by_id(self) -> dict[str, Order]:
        return {o.id: o for o in self.orders}

    @property
    def engineer_by_id(self) -> dict[str, Engineer]:
        return {e.id: e for e in self.engineers}

    def summary(self) -> dict[str, object]:
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
            "urgent": sum(1 for o in self.orders if o.priority == PRIORITY_URGENT),
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
    crews: dict[str, CrewFacts] = {}
    # В выгрузках встречается один и тот же номер заявки в двух строках с
    # разными временными окнами — это два визита по одному адресу. Разводим их
    # в отдельные заявки, иначе одна из них потерялась бы при любом поиске по id.
    seen_ids: dict[str, int] = {}
    duplicates: list[str] = []
    skipped: list[dict[str, str]] = []

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
            facts = crews.setdefault(crew, CrewFacts())
            facts.skills.add(order.required_skill)
            facts.points.append((lat, lon))
            facts.windows.append((start, end))
            facts.districts.add(order.district)
            if order.required_vehicle == VEHICLE_CAR:
                facts.needs_car = True

    engineers = build_engineers(crews)
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


def load_all(raw_dir: str, cache_path: str) -> dict[str, Scenario]:
    return {key: load_scenario(key, raw_dir, cache_path) for key in REGIONS}
