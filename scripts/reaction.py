#!/usr/bin/env python3
"""Замер реакции на аварию, поступившую днём: источник чисел README.

На каждом участке строится утренний план, затем в 11, 13 и 15 часов в центр
заявок участка поступает авария, и событие считается в обоих режимах. Для
каждого случая печатается, кто взял аварию и через сколько минут приедет;
в конце - сколько встало, сколько уложилось в срок и самое долгое.

    python scripts/reaction.py

Утренний план останавливается по числу решений и повторяется; полная
пересборка ограничена минутой, поэтому её числа могут слегка отличаться
между машинами.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from dispatcher.domain.catalog import SKILL_EMERGENCY  # noqa: E402
from dispatcher.services.planning.optimizer import solve_optimized  # noqa: E402
from dispatcher.services.replanning.apply import replan  # noqa: E402
from dispatcher.services.replanning.events import (  # noqa: E402
    KIND_URGENT,
    ReplanEvent,
    make_new_order,
)
from dispatcher.services.replanning.repair import MODE_FULL, MODE_MINIMAL  # noqa: E402
from dispatcher.services.scenario import load_all  # noqa: E402

HOURS = (11, 13, 15)
DURATION_MIN = 80


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    scenarios = load_all(os.path.join(ROOT, "data", "raw"),
                         os.path.join(ROOT, "data", "geo_cache.json"))
    minutes: list[int | None] = []
    late: list[str] = []
    for scenario in scenarios.values():
        orders, crews = scenario.orders, scenario.engineers
        plan = solve_optimized(orders, crews)
        lat = sum(o.lat for o in orders) / len(orders)
        lon = sum(o.lon for o in orders) / len(orders)
        for hour in HOURS:
            at = hour * 60
            crash = make_new_order(f"АВАРИЯ-{hour}", lat, lon, "центр заявок",
                                   orders[0].district, DURATION_MIN, at, 23 * 60 + 59,
                                   SKILL_EMERGENCY)
            for mode in (MODE_MINIMAL, MODE_FULL):
                result = replan(orders, crews, plan,
                                ReplanEvent(KIND_URGENT, at, new_order=crash), mode=mode)
                info = result.diff.get("reaction")
                case = f"{scenario.region_name}, {hour}:00, {mode}"
                if info is None:
                    minutes.append(None)
                    print(f"  {case}: не встала")
                    continue
                minutes.append(int(info["minutes"]))
                if not info["within"]:
                    late.append(case)
                print(f"  {case}: «{info['engineer_id']}», через {info['minutes']} мин"
                      + ("" if info["within"] else ", дольше срока"))
    placed = [m for m in minutes if m is not None]
    print(f"\nСлучаев {len(minutes)}, встала {len(placed)}, в срок "
          f"{len(placed) - len(late)}, в среднем {round(sum(placed) / len(placed))} мин, "
          f"самое долгое {max(placed)} мин.")
    for case in late:
        print(f"  дольше срока: {case}")
    return 0 if len(placed) == len(minutes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
