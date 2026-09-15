#!/usr/bin/env python3
"""Замер, из которого берутся все цифры в README и презентации.

Скрипт существует, чтобы ни одно число в документации не появлялось «из
головы»: таблицу сравнения вариантов плана можно воспроизвести одной командой
и сверить с тем, что написано.

    python scripts/benchmark.py [--time-limit 15] [--runs 1] [--heuristics]

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
    os.path.abspath(__file__))), "backend"))

from ingest import load_all                                   # noqa: E402
from metrics import control_plan, plan_metrics                # noqa: E402
from solver import (STRATEGY_FULL_TITLES, solve_baseline,     # noqa: E402
                    solve_greedy, solve_optimized)
from validate import validate                                 # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(ROOT, "data", "raw")
CACHE_PATH = os.path.join(ROOT, "data", "geo_cache.json")


def _brigades(count: int) -> str:
    """Склонение слова «бригада» по числу: 1 бригада, 2 бригады, 5 бригад."""
    if count % 100 in range(11, 15):
        return "бригад"
    return {1: "бригада", 2: "бригады", 3: "бригады", 4: "бригады"}.get(
        count % 10, "бригад")


def _row(title: str, metrics: dict, ok: bool | None) -> dict:
    return {
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

    for title, solver in (
        (STRATEGY_FULL_TITLES["baseline"], solve_baseline),
        (STRATEGY_FULL_TITLES["greedy"], solve_greedy),
    ):
        plan = solver(orders, engineers)
        rows.append(_row(title, plan_metrics(plan, orders, engineers),
                         validate(plan, orders, engineers).ok))

    # оптимизатор — столько прогонов, сколько попросили, с разбросом
    trials = []
    for _ in range(runs):
        plan = solve_optimized(orders, engineers, time_limit_sec=time_limit)
        trials.append((plan_metrics(plan, orders, engineers),
                       validate(plan, orders, engineers).ok))
    best = min(trials, key=lambda t: (-t[0]["orders_assigned"],
                                      t[0]["used_engineers"], t[0]["total_km"]))
    row = _row(STRATEGY_FULL_TITLES["optimized"], best[0], best[1])
    if runs > 1:
        row["spread"] = {
            "assigned": sorted({t[0]["orders_assigned"] for t in trials}),
            "used": sorted({t[0]["used_engineers"] for t in trials}),
            "km": [round(min(t[0]["total_km"] for t in trials), 1),
                   round(max(t[0]["total_km"] for t in trials), 1)],
            "km_median": round(statistics.median(t[0]["total_km"] for t in trials), 1),
        }
    rows.append(row)

    fact, fact_report = control_plan(orders, engineers)
    fact_row = _row("Факт: живой диспетчер",
                    plan_metrics(fact, orders, engineers), None)
    fact_row["fact_report"] = fact_report
    rows.append(fact_row)
    return rows


def sweep_heuristics(scenarios, time_limit: int) -> None:
    """Перебор эвристик первого решения — тем же замером, что и всё остальное.

    Настройки поиска в `backend/solver.py` выбраны не из примеров OR-Tools, и
    эта таблица — то, чем выбор подтверждается. Метаэвристика локального поиска
    при этом не меняется: сравниваются именно стартовые решения.
    """
    import solver
    from ortools.constraint_solver import routing_enums_pb2

    names = ["SAVINGS", "PARALLEL_CHEAPEST_INSERTION", "PATH_CHEAPEST_ARC",
             "CHRISTOFIDES", "LOCAL_CHEAPEST_INSERTION"]
    print(f"\n\nЭвристики первого решения, {time_limit} с на район "
          f"(выбрана {solver.FIRST_SOLUTION_NAME}):\n")
    print("| Район | Эвристика | Назначено | Исполнителей | Пробег, км |")
    print("|---|---|---|---|---|")

    original = solver.FIRST_SOLUTION
    try:
        for scenario in scenarios.values():
            for i, name in enumerate(names):
                solver.FIRST_SOLUTION = getattr(
                    routing_enums_pb2.FirstSolutionStrategy, name)
                plan = solver.solve_optimized(
                    scenario.orders, scenario.engineers, time_limit_sec=time_limit)
                m = plan_metrics(plan, scenario.orders, scenario.engineers)
                wrap = "**" if name == solver.FIRST_SOLUTION_NAME else ""
                region = scenario.region_name if i == 0 else ""
                print(f"| {region} | {wrap}{name}{wrap} "
                      f"| {wrap}{m['orders_assigned']}/{m['orders_total']}{wrap} "
                      f"| {wrap}{m['used_engineers']}{wrap} "
                      f"| {wrap}{m['total_km']:.1f}{wrap} |")
    finally:
        solver.FIRST_SOLUTION = original


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--time-limit", type=int, default=15,
                        help="секунд на район для оптимизатора")
    parser.add_argument("--runs", type=int, default=1,
                        help="сколько раз прогнать оптимизатор")
    parser.add_argument("--heuristics", action="store_true",
                        help="дополнительно перебрать эвристики первого решения")
    args = parser.parse_args()

    scenarios = load_all(RAW_DIR, CACHE_PATH)
    print(f"Лимит времени оптимизатора — {args.time_limit} с на район, "
          f"прогонов: {args.runs}\n")
    print("| Район | Вариант | Назначено | Исполнителей | Пробег, км | Км на заявку |")
    print("|---|---|---|---|---|---|")

    summary: dict[str, dict] = {}
    for key, scenario in scenarios.items():
        rows = measure(scenario, args.time_limit, args.runs)
        summary[scenario.region_name] = {r["title"]: r for r in rows}
        for i, r in enumerate(rows):
            region = scenario.region_name if i == 0 else ""
            mark = "**" if "OR-Tools" in r["title"] else ""
            italic = "*" if r["title"].startswith("Факт") else ""
            wrap = mark or italic
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

    print("\n\nОптимизатор против базового варианта и против факта "
          "— по километрам на одну назначенную заявку:\n")
    print("| Район | Против базового | Против факта |")
    print("|---|---|---|")
    for region, rows in summary.items():
        opt = next(r for t, r in rows.items() if "OR-Tools" in t)
        base = next(r for t, r in rows.items() if "базовый" in t)
        fact = next(r for t, r in rows.items() if t.startswith("Факт"))
        def delta(other):
            if not other["km_per_order"]:
                return "—"
            return f"{round(100 * (opt['km_per_order'] / other['km_per_order'] - 1)):+d}% км на заявку"
        people = opt["used"] - fact["used"]
        # Таблицу переносят в README дословно, поэтому склонение здесь, а не
        # «−1 бригад» с последующей ручной правкой.
        people_text = (f", {people:+d} {_brigades(abs(people))}"
                       if people else ", столько же бригад")
        print(f"| {region} | {delta(base)} | {delta(fact)}{people_text} |")

    print("\n\nФактическое распределение против правил ТЗ:\n")
    for region, rows in summary.items():
        fact = next(r for t, r in rows.items() if t.startswith("Факт"))
        report = fact.get("fact_report") or {}
        print(f"  {region}: нарушений окна "
              f"{len(report.get('window_violations') or [])}, "
              f"выходов за смену {len(report.get('shift_overflow') or [])}, "
              f"максимум заявок в одно окно одной бригаде "
              f"{report.get('max_orders_per_window_per_crew', '?')}, "
              f"заявок без бригады {len(report.get('orders_without_crew') or [])}")

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
