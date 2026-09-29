"""Чтение синтетической выгрузки участка: заявки и адрес офиса.

Постановщик назвал синтетические данные единственным входом планирования, а
контрольное распределение - ориентиром «как было в жизни». Поэтому здесь нет
ни бригад, ни статусов: в файле их и нет.

Адрес офиса лежит отдельной строкой в хвосте файла и служит стартовой точкой
дня: там бригада получает оборудование.
"""
from __future__ import annotations

import csv
import io
import os
from dataclasses import dataclass, field

from dispatcher.domain import Order
from dispatcher.infrastructure.csvfile import CSV_DELIMITER, decode_csv
from dispatcher.infrastructure.geo import Geocoder
from dispatcher.infrastructure.geo_online import Fetch, fill_missing
from dispatcher.infrastructure.orders_csv import (
    OFFICE_MARKER,
    parse_orders,
    read_rows,
    row_places,
)


@dataclass
class SyntheticInput:
    """Вход планирования по одному участку."""

    region_key: str
    orders: list[Order] = field(default_factory=list)
    office_address: str = ""
    office_lat: float = 0.0
    office_lon: float = 0.0
    duplicate_ids: list[str] = field(default_factory=list)
    skipped_rows: list[dict[str, str]] = field(default_factory=list)
    geo_report: dict[str, object] = field(default_factory=dict)


def read_office_address(text: str) -> str:
    """Адрес офиса участка из хвоста выгрузки."""
    for row in csv.reader(io.StringIO(text), delimiter=CSV_DELIMITER):
        if row and OFFICE_MARKER in row[0].strip().lower():
            return row[1].strip() if len(row) > 1 else ""
    return ""


def parse_synthetic(raw: bytes, region_key: str, cache_path: str,
                    fetch: Fetch | None = None) -> SyntheticInput:
    """Разбирает синтетическую выгрузку из байтов файла.

    `fetch` - геокодер для адресов, которых нет в кэше; без него такие
    адреса ставятся в центр района.
    """
    text = decode_csv(raw)
    geocoder = Geocoder(cache_path)
    rows = read_rows(text)
    address = read_office_address(text)
    if fetch is not None:
        fill_missing(geocoder, [*row_places(rows), (address, "")], fetch)
    parsed = parse_orders(rows, geocoder)

    # Офис участка стоит вне района заявок: на Юго-востоке он в Бирюлёво, а
    # заявки доходят до Каширы. Сверять его координату с районом нельзя,
    # иначе верная точка будет отвергнута как неправдоподобная.
    district = parsed.orders[0].district if parsed.orders else ""
    lat, lon = 0.0, 0.0
    if address:
        lat, lon, _ = geocoder.locate(address, district, check_district=False)
    if (lat, lon) == (0.0, 0.0) and parsed.orders:
        # Без офиса в файле бригады стартовали бы с нулевой точки у экватора.
        # Центр заявок участка - честное приближение, и в допущениях оно названо.
        lat = sum(o.lat for o in parsed.orders) / len(parsed.orders)
        lon = sum(o.lon for o in parsed.orders) / len(parsed.orders)

    return SyntheticInput(
        region_key=region_key,
        orders=parsed.orders,
        office_address=address,
        office_lat=lat,
        office_lon=lon,
        duplicate_ids=parsed.duplicate_ids,
        skipped_rows=parsed.skipped_rows,
        geo_report=geocoder.report(),
    )


def load_synthetic(region_key: str, raw_dir: str, cache_path: str) -> SyntheticInput:
    """Читает синтетическую выгрузку участка из каталога с данными."""
    path = os.path.join(raw_dir, f"{region_key}_synth.csv")
    with open(path, "rb") as fh:
        raw = fh.read()
    return parse_synthetic(raw, region_key, cache_path)
