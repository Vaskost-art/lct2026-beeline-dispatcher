#!/usr/bin/env python3
"""Замер, из которого берутся все цифры в README и презентации.

Скрипт существует, чтобы ни одно число в документации не появлялось «из
головы»: таблицу сравнения вариантов плана можно воспроизвести одной командой
и сверить с тем, что написано.

    python scripts/benchmark.py [--time-limit 300] [--runs 1] [--heuristics]

Несколько прогонов (--runs) нужны там, где важен разброс: поиск эвристический,
и на границе «вывести ещё одного человека или проехать лишние километры»
решатель может честно качнуться в обе стороны.
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))

from dispatcher.services.metrics import plan_metrics  # noqa: E402
from dispatcher.services.planning.baseline import solve_baseline, solve_greedy  # noqa: E402
from dispatcher.services.planning.costs import DEFAULT_TIME_LIMIT_SEC  # noqa: E402
from dispatcher.services.planning.optimizer import solve_optimized  # noqa: E402
from dispatcher.services.planning.strategies import STRATEGY_FULL_TITLES  # noqa: E402
from dispatcher.services.scenario import load_all  # noqa: E402
from dispatcher.services.validate import validate  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(ROOT, "data", "raw")
CACHE_PATH = os.path.join(ROOT, "data", "geo_cache.json")


def _row(title: str, metrics: dict, ok: bool | None, key: str = "") -> dict:
    return {
        "key": key,
        "title": title,
        "assigned": metrics["orders_assigned"],
        "total": metrics["orders_total"],
        "used": metrics["used_engineers"],
        "available": metrics["engineers_available"],
        "km": metrics["total_km"],
        "km_per_order": metrics["avg_km_per_order"],
        "valid": ok,
    }


def measure(scenario, time_limit: int, runs: int) -> list[dict]:
    orders, engineers = scenario.orders, scenario.engineers
    rows: list[dict] = []

    for key, solver in (("baseline", solve_baseline), ("greedy", solve_greedy)):
        plan = solver(orders, engineers)
        rows.append(_row(STRATEGY_FULL_TITLES[key], plan_metrics(plan, orders, engineers),
                         validate(plan, orders, engineers).ok, key))

    # оптимизатор - столько прогонов, сколько попросили, с разбросом
    trials = []
    for _ in range(runs):
        plan = solve_optimized(orders, engineers, time_limit_sec=time_limit)
        trials.append((plan_metrics(plan, orders, engineers),
                       validate(plan, orders, engineers).ok))
    best = min(trials, key=lambda t: (-t[0]["orders_assigned"],
                                      t[0]["used_engineers"], t[0]["total_km"]))
    row = _row(STRATEGY_FULL_TITLES["optimized"], best[0], best[1], "optimized")
    if runs > 1:
        row["spread"] = {
            "assigned": sorted({t[0]["orders_assigned"] for t in trials}),
            "used": sorted({t[0]["used_engineers"] for t in trials}),
            "km": [round(min(t[0]["total_km"] for t in trials), 1),
                   round(max(t[0]["total_km"] for t in trials), 1)],
            "km_median": round(statistics.median(t[0]["total_km"] for t in trials), 1),
        }
    rows.append(row)
    return rows


def sweep_heuristics(scenarios, time_limit: int) -> None:
    """Перебор эвристик первого решения - тем же замером, что и всё остальное.

    Настройки поиска в `dispatcher/services/planning` выбраны не из примеров OR-Tools, и
    эта таблица - то, чем выбор подтверждается. Метаэвристика локального поиска
    при этом не меняется: сравниваются именно стартовые решения.
    """
    from ortools.constraint_solver import routing_enums_pb2

    from dispatcher.services.planning import optimizer, search

    names = ["SAVINGS", "PARALLEL_CHEAPEST_INSERTION", "PATH_CHEAPEST_ARC",
             "CHRISTOFIDES", "LOCAL_CHEAPEST_INSERTION"]
    print(f"\n\nЭвристики первого решения, {time_limit} с на район "
          f"(выбрана {search.FIRST_SOLUTION_NAME}):\n")
    print("| Район | Эвристика | Назначено | Исполнителей | Пробег, км |")
    print("|---|---|---|---|---|")

    original = optimizer.FIRST_SOLUTION
    try:
        for scenario in scenarios.values():
            for i, name in enumerate(names):
                # Подменяется имя, уже импортированное оптимизатором: правка
                # самого `search` до него не доходит - имя связано при импорте.
                optimizer.FIRST_SOLUTION = getattr(
                    routing_enums_pb2.FirstSolutionStrategy, name)
                plan = optimizer.solve_optimized(
                    scenario.orders, scenario.engineers, time_limit_sec=time_limit)
                m = plan_metrics(plan, scenario.orders, scenario.engineers)
                wrap = "**" if name == search.FIRST_SOLUTION_NAME else ""
                region = scenario.region_name if i == 0 else ""
                print(f"| {region} | {wrap}{name}{wrap} "
                      f"| {wrap}{m['orders_assigned']}/{m['orders_total']}{wrap} "
                      f"| {wrap}{m['used_engineers']}{wrap} "
                      f"| {wrap}{m['total_km']:.1f}{wrap} |")
    finally:
        optimizer.FIRST_SOLUTION = original


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--time-limit", type=int, default=DEFAULT_TIME_LIMIT_SEC,
                        help="секунд на район для оптимизатора")
    parser.add_argument("--runs", type=int, default=1,
                        help="сколько раз прогнать оптимизатор")
    parser.add_argument("--heuristics", action="store_true",
                        help="дополнительно перебрать эвристики первого решения")
    args = parser.parse_args()

    scenarios = load_all(RAW_DIR, CACHE_PATH)
    print(f"Лимит времени оптимизатора - {args.time_limit} с на район, "
          f"прогонов: {args.runs}\n")
    print("| Район | Вариант | Назначено | Исполнителей | Пробег, км | Км на заявку |")
    print("|---|---|---|---|---|---|")

    summary: dict[str, dict] = {}
    for scenario in scenarios.values():
        rows = measure(scenario, args.time_limit, args.runs)
        summary[scenario.region_name] = {r["title"]: r for r in rows}
        for i, r in enumerate(rows):
            region = scenario.region_name if i == 0 else ""
            wrap = "**" if r["key"] == "optimized" else ""
            km = f"{r['km']:.1f}"
            print(f"| {region} | {wrap}{r['title']}{wrap} "
                  f"| {wrap}{r['assigned']}/{r['total']}{wrap} "
                  f"| {wrap}{r['used']} из {r['available']}{wrap} "
                  f"| {wrap}{km}{wrap} | {wrap}{r['km_per_order']:.2f}{wrap} |")
            if r.get("spread"):
                print(f"|  | *разброс по {args.runs} прогонам* "
                      f"| {'/'.join(map(str, r['spread']['assigned']))} "
                      f"| {'/'.join(map(str, r['spread']['used']))} "
                      f"| {r['spread']['km'][0]}–{r['spread']['km'][1]} "
                      f"(медиана {r['spread']['km_median']}) |  |")

    print("\n\nОптимизатор против базового варианта:\n")
    print("| Район | Заявок больше | Км на заявку |")
    print("|---|---|---|")
    for region, rows in summary.items():
        opt = next(r for r in rows.values() if r["key"] == "optimized")
        base = next(r for r in rows.values() if r["key"] == "baseline")
        change = (f"{round(100 * (opt['km_per_order'] / base['km_per_order'] - 1)):+d}%"
                  if base["km_per_order"] else "-")
        print(f"| {region} | {opt['assigned'] - base['assigned']:+d} | {change} |")

    if args.heuristics:
        sweep_heuristics(scenarios, args.time_limit)

    bad = [(region, title) for region, rows in summary.items()
           for title, r in rows.items() if r["valid"] is False]
    if bad:
        print("\nПЛАНЫ, НЕ ПРОШЕДШИЕ ПРОВЕРКУ:", bad)
        return 1
    print("\nВсе построенные планы прошли независимую проверку ограничений.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
