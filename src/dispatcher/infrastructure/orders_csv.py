"""Разбор строк заявок, общий для синтетической и контрольной выгрузок.

Форматы отличаются только дополнительными колонками контрольной выгрузки
(«Бригада», «Статус BK») и хвостом синтетической (адрес офиса участка). Сама
заявка собирается одинаково, поэтому разбор живёт в одном месте: иначе два
описания одной строки со временем разойдутся.
"""
from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from dispatcher.domain import Order, norms
from dispatcher.domain.distance import normalize_district
from dispatcher.domain.equipment import equipment_for
from dispatcher.infrastructure.csvfile import (
    CSV_DELIMITER,
    _cell,
    _clean_address,
    _parse_dt,
)
from dispatcher.infrastructure.geo import Geocoder

#: Окно «0:01–23:59» и прочие сутки приводим к концу дня.
END_OF_DAY = 23 * 60 + 59


@dataclass
class ParsedOrders:
    """Что дал разбор выгрузки, включая то, что разобрать не удалось."""

    orders: list[Order] = field(default_factory=list)
    duplicate_ids: list[str] = field(default_factory=list)
    skipped_rows: list[dict[str, str]] = field(default_factory=list)
    rows: list[Mapping[str, str | None]] = field(default_factory=list)


#: Как подписана строка с адресом офиса в хвосте выгрузки.
OFFICE_MARKER = "адрес офиса"


def row_places(rows: Sequence[Mapping[str, str | None]]) -> list[tuple[str, str]]:
    """Адрес и район каждой строки: то, что ищет геокодер."""
    return [(_clean_address(_cell(row, "Адрес")), _cell(row, "Район")) for row in rows]


def read_rows(text: str) -> list[Mapping[str, str | None]]:
    """Строки заявок: с непустым номером и без строки офиса.

    Строка офиса стоит в колонке «Заявка», и без этого фильтра она попадала в
    список пропущенных нарядов у каждого участка.
    """
    return [
        row for row in csv.DictReader(io.StringIO(text), delimiter=CSV_DELIMITER)
        if (number := (row.get("Заявка") or "").strip())
        and OFFICE_MARKER not in number.lower()
    ]


def parse_orders(rows: list[Mapping[str, str | None]],
                 geocoder: Geocoder) -> ParsedOrders:
    """Собирает заявки из строк выгрузки.

    Строка с неразобранным временем не теряется молча: она попадает в список
    пропущенных, потому что иначе план выглядит полным, а наряда в нём нет.
    """
    result = ParsedOrders(rows=rows)
    seen_ids: dict[str, int] = {}

    for row in rows:
        order_id = _cell(row, "Заявка")
        district = _cell(row, "Район")
        address = _clean_address(_cell(row, "Адрес"))
        start = _parse_dt(_cell(row, "Начало"))
        end = _parse_dt(_cell(row, "Окончание"))
        if start is None or end is None:
            result.skipped_rows.append({"order_id": order_id,
                                        "start": _cell(row, "Начало"),
                                        "end": _cell(row, "Окончание")})
            continue

        seen_ids[order_id] = seen_ids.get(order_id, 0) + 1
        if seen_ids[order_id] > 1:
            # Один номер в двух строках с разными окнами это два визита по
            # одному адресу. Разводим их, иначе один потеряется при поиске.
            result.duplicate_ids.append(order_id)
            order_id = f"{order_id}-{seen_ids[order_id]}"
        if end <= start:
            end = END_OF_DAY

        type_bk = _cell(row, "Тип заявки BK")
        type_hd = _cell(row, "Тип заявки HD")
        status_bk = _cell(row, "Статус BK")
        gigabit = _cell(row, "Гигабитное подключение").lower() == "да"
        crew = _cell(row, "Бригада")

        lat, lon, precision = geocoder.locate(address, district)
        result.orders.append(Order(
            id=order_id,
            lat=lat,
            lon=lon,
            address=address,
            district=normalize_district(district),
            duration_min=norms.duration_for(type_bk),
            window_start=start,
            window_end=end,
            priority=norms.priority_for(type_bk, status_bk),
            required_skill=norms.skill_for(type_bk),
            required_vehicle=norms.required_vehicle_for(type_hd, gigabit),
            equipment=equipment_for(type_bk, type_hd, order_id),
            type_bk=type_bk,
            type_hd=type_hd,
            control_engineer=crew or None,
            geocode_precision=precision,
        ))
    return result
