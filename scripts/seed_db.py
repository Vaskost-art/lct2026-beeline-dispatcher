#!/usr/bin/env python3
"""Первичное наполнение базы: кэш координат и участки.

Координаты собирались через Nominatim один раз и лежат в
`data/geo_cache.json`. Терять их нельзя: без них сервис считает адреса
приблизительно, по центру района.

Запуск: python scripts/seed_db.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from dispatcher.infrastructure.db.repositories import (  # noqa: E402
    GeoRepository,
    RegionRepository,
)
from dispatcher.infrastructure.db.session import dispose, session  # noqa: E402
from dispatcher.infrastructure.ingest import REGIONS  # noqa: E402
from dispatcher.infrastructure.synthetic import load_synthetic  # noqa: E402

RAW_DIR = os.path.join(ROOT, "data", "raw")
CACHE_PATH = os.path.join(ROOT, "data", "geo_cache.json")


async def seed_geo(active) -> int:
    """Переносит кэш координат из файла в базу."""
    if not os.path.exists(CACHE_PATH):
        return 0
    with open(CACHE_PATH, encoding="utf-8") as fh:
        cache = json.load(fh)
    geo = GeoRepository(active)
    for key, value in cache.items():
        await geo.put(key, value.get("lat"), value.get("lon"),
                      str(value.get("source") or ""), str(value.get("query") or ""))
    return len(cache)


async def seed_regions(active) -> int:
    """Записывает участки задачи с их заявками и офисом."""
    regions = RegionRepository(active)
    for key, name in REGIONS.items():
        data = load_synthetic(key, RAW_DIR, CACHE_PATH)
        await regions.save(
            key, name,
            {"orders": [order.to_dict() for order in data.orders]},
            data.office_address, data.office_lat, data.office_lon)
    return len(REGIONS)


async def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    async with session() as active:
        points = await seed_geo(active)
        regions = await seed_regions(active)
        await active.commit()
    await dispose()
    print(f"Координат перенесено: {points}")
    print(f"Участков записано: {regions}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
