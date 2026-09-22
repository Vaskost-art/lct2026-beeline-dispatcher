#!/usr/bin/env python3
"""Сворачивает рабочие дни участков: день начинается с чистого листа.

Нужно перед съёмкой экранов (состояние «план ещё не построен» достижимо
только на участке без плана) и при отладке. Записи не удаляются физически,
а помечаются свёрнутыми: историю дня не стирают.

Запуск: python scripts/clear_day.py [участок ...]
Без участков сворачивает все.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from dispatcher.infrastructure.db.repositories import (  # noqa: E402
    PlanRepository,
    RegionRepository,
)
from dispatcher.infrastructure.db.session import dispose, session  # noqa: E402


def main(keys: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    with session() as active:
        regions = RegionRepository(active)
        plans = PlanRepository(active)
        chosen = ([region for key in keys
                   if (region := regions.by_key(key)) is not None]
                  if keys else regions.list())
        for region in chosen:
            print(f"{region.key}: свёрнуто версий {plans.drop_all(region.id)}")
        active.commit()
    dispose()
    if keys and not chosen:
        print("Таких участков в базе нет")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
