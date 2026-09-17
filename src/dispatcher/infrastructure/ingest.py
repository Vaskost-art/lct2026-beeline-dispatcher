"""Чтение контрольного распределения: ориентир «как было в жизни».

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

from dispatcher.domain import (
    VEHICLE_CAR,
    Order,
    norms,
)
from dispatcher.domain.distance import normalize_district
from dispatcher.domain.scenario import Scenario
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


def load_control_scenario(region_key: str, raw_dir: str, cache_path: str) -> Scenario:
    """Читает контрольное распределение: ориентир «как было в жизни»."""
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


def load_all_control(raw_dir: str, cache_path: str) -> dict[str, Scenario]:
    """Контрольные распределения по всем участкам."""
    return {key: load_control_scenario(key, raw_dir, cache_path)
            for key in REGIONS}
