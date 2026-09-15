#!/usr/bin/env python3
"""Сквозная самопроверка: строит все планы по всем районам и аудирует каждый.

Проверяется то, о чём эксперты спрашивают прямо:
  * обязательные ограничения действительно соблюдаются — каждый план
    независимо перепроверяется модулем validate;
  * все три события перепланирования отрабатывают в обоих режимах, и
    результат снова проходит проверку;
  * заявка не может быть одновременно назначенной и неназначенной,
    а у каждой неназначенной есть причина.

Запуск:  python3 scripts/selftest.py
Код возврата 0 — всё в порядке, 1 — найдены нарушения.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))

from dataset import scenario_from_json, scenario_to_json       # noqa: E402
from ingest import load_all                                    # noqa: E402
from metrics import control_plan, plan_metrics                 # noqa: E402
from replan import (KIND_CANCEL, KIND_DELAYED, KIND_UNAVAILABLE,  # noqa: E402
                    KIND_URGENT, MODE_FULL, MODE_MINIMAL, ReplanEvent,
                    make_urgent_order, replan)
from risk import plan_risk                                     # noqa: E402
from solver import solve_baseline, solve_greedy, solve_optimized  # noqa: E402
from validate import validate                                  # noqa: E402

RAW_DIR = os.path.join(ROOT, "data", "raw")
CACHE = os.path.join(ROOT, "data", "geo_cache.json")
TIME_LIMIT = int(os.environ.get("SELFTEST_TIME_LIMIT", "8"))

failures: list[str] = []


def check(label: str, plan, orders, engineers) -> None:
    report = validate(plan, orders, engineers)
    status = "ок" if report.ok else f"НАРУШЕНИЯ {report.by_rule()}"
    print(f"      проверка: {status} "
          f"(маршрутов {report.checked_routes}, визитов {report.checked_stops})")
    if not report.ok:
        failures.append(label)
        for violation in report.violations[:5]:
            print(f"         · {violation.rule}: {violation.text}")


def main() -> int:
    scenarios = load_all(RAW_DIR, CACHE)
    print(f"Загружено районов: {len(scenarios)}\n")

    for scenario in scenarios.values():
        summary = scenario.summary()
        print("=" * 78)
        print(f"{scenario.region_name}: {summary['orders']} заявок, "
              f"{summary['engineers']} исполнителей, "
              f"срочных {summary['urgent']}, "
              f"с требованием транспорта {summary['with_vehicle_requirement']}")
        print(f"  навыки: {summary['orders_by_skill']}")
        print(f"  транспорт исполнителей: {summary['engineers_by_vehicle']}")
        if summary["duplicate_ids"]:
            print(f"  дубликаты номеров в данных (разведены): "
                  f"{summary['duplicate_ids']}")
        geo = summary["geocoding"]
        print(f"  геокодирование: точных {geo['exact']}, "
              f"приблизительных {geo['approx']} "
              f"(покрытие {geo['coverage'] * 100:.0f}%)")

        orders, engineers = scenario.orders, scenario.engineers

        fact, fact_report = control_plan(orders, engineers)
        fact_metrics = plan_metrics(fact, orders, engineers)
        print(f"\n  ФАКТ (живой диспетчер): исполнителей "
              f"{fact_metrics['used_engineers']}, "
              f"пробег {fact_metrics['total_km']:.1f} км, "
              f"назначено {fact_metrics['orders_assigned']}")
        print(f"      нарушений окна в факте: "
              f"{len(fact_report['window_violations'])}, "
              f"выходов за смену: {len(fact_report['shift_overflow'])}, "
              f"максимум заявок в одно окно одной бригаде: "
              f"{fact_report['max_orders_per_window_per_crew']}")

        plans = {}
        print()
        for key, title, fn in (
            ("baseline", "базовый вариант по ТЗ", solve_baseline),
            ("greedy", "жадная эвристика", solve_greedy),
            ("optimized", "оптимизатор OR-Tools", solve_optimized),
        ):
            plan = (fn(orders, engineers, time_limit_sec=TIME_LIMIT)
                    if key == "optimized" else fn(orders, engineers))
            metrics = plan_metrics(plan, orders, engineers)
            plans[key] = plan
            print(f"  {title}: назначено {metrics['orders_assigned']}/"
                  f"{metrics['orders_total']}, "
                  f"исполнителей {metrics['used_engineers']}, "
                  f"пробег {metrics['total_km']:.1f} км, "
                  f"расчёт {metrics['solve_seconds']:.2f} с")
            check(f"{scenario.region_name}/{key}", plan, orders, engineers)

        base = plan_metrics(plans["baseline"], orders, engineers)
        best = plan_metrics(plans["optimized"], orders, engineers)
        print(f"\n  оптимизатор против базового варианта: "
              f"заявок {best['orders_assigned'] - base['orders_assigned']:+d}, "
              f"исполнителей {best['used_engineers'] - base['used_engineers']:+d}, "
              f"пробег {best['total_km'] - base['total_km']:+.1f} км")
        print(f"  оптимизатор против факта: "
              f"исполнителей "
              f"{best['used_engineers'] - fact_metrics['used_engineers']:+d}, "
              f"пробег {best['total_km'] - fact_metrics['total_km']:+.1f} км")

        # --- обмен набором данных: запись и чтение без потерь ---
        blob = scenario_to_json(scenario)
        restored, _ = scenario_from_json(blob, scenario.region_key)
        same_orders = ([(o.id, o.window_start, o.window_end, o.duration_min,
                         o.required_skill, o.required_vehicle, o.priority)
                        for o in orders]
                       == [(o.id, o.window_start, o.window_end, o.duration_min,
                            o.required_skill, o.required_vehicle, o.priority)
                           for o in restored.orders])
        same_engineers = ([(e.id, tuple(e.skills), e.vehicle,
                            e.shift_start, e.shift_end) for e in engineers]
                          == [(e.id, tuple(e.skills), e.vehicle,
                               e.shift_start, e.shift_end)
                              for e in restored.engineers])
        if same_orders and same_engineers:
            print("\n  обмен набором данных: запись и чтение без потерь — ок")
        else:
            print("\n  обмен набором данных: РАСХОЖДЕНИЕ после круга запись-чтение")
            failures.append(f"{scenario.region_name}/dataset-roundtrip")

        # --- прогноз опозданий ---
        report = plan_risk(plans["optimized"], orders, engineers)
        weakest = report["weakest_route"]
        print(f"  прогноз опозданий: {report['by_risk']}, "
              f"самый хрупкий маршрут — «{weakest['engineer_id']}», "
              f"запас {weakest['tolerance_min']} мин")
        for scenario_row in report["scenarios"]:
            print(f"    при просадке {scenario_row['overrun_per_job']} мин: "
                  f"под угрозой {scenario_row['broken_count']} заявок")
        # запас не может превышать сам себя и обязан быть неотрицательным
        bad_risk = [r for r in report["routes"]
                    if r["tolerance_min"] < 0
                    or r["tolerance_min"] > r["start_tolerance_min"]]
        if bad_risk:
            print(f"    НЕКОРРЕКТНЫЙ ЗАПАС у {len(bad_risk)} маршрутов")
            failures.append(f"{scenario.region_name}/risk")

        # --- события перепланирования ---
        current = plans["optimized"]
        busiest = max(current.routes, key=lambda r: len(r.stops)).engineer_id
        first_assigned = next(s.order_id for r in current.routes
                              if r.stops for s in r.stops)
        urgent = make_urgent_order(
            order_id="SELFTEST-URGENT",
            lat=orders[0].lat, lon=orders[0].lon,
            address="Проверочная точка", district=orders[0].district,
            duration_min=60, window_start=15 * 60, window_end=17 * 60,
            required_skill=orders[0].required_skill,
        )

        events = [
            ("срочная заявка",
             ReplanEvent(KIND_URGENT, 13 * 60, new_order=urgent)),
            ("отмена заявки",
             ReplanEvent(KIND_CANCEL, 12 * 60, order_id=first_assigned)),
            ("инженер недоступен",
             ReplanEvent(KIND_UNAVAILABLE, 13 * 60, engineer_id=busiest)),
            ("бригада задерживается",
             ReplanEvent(KIND_DELAYED, 13 * 60, engineer_id=busiest,
                         delay_min=60)),
        ]

        print("\n  перепланирование:")
        for title, event in events:
            for mode in (MODE_MINIMAL, MODE_FULL):
                result = replan(orders, engineers, current, event, mode=mode,
                                time_limit_sec=TIME_LIMIT)
                after = result.orders
                metrics = plan_metrics(result.plan, after, result.engineers)
                counts = result.diff["counts"]
                churn = counts.get("moved", 0) + counts.get("resequenced", 0)
                print(f"    {title} / {mode}: назначено "
                      f"{metrics['orders_assigned']}/{metrics['orders_total']}, "
                      f"исполнителей {metrics['used_engineers']}, "
                      f"пробег {metrics['total_km']:.1f} км, "
                      f"перестановок {churn}")
                check(f"{scenario.region_name}/{event.kind}/{mode}",
                      result.plan, after, result.engineers)
        print()

    print("=" * 78)
    if failures:
        print(f"НАЙДЕНЫ НАРУШЕНИЯ в {len(failures)} планах:")
        for name in failures:
            print(f"  · {name}")
        return 1
    print("Все планы прошли независимую проверку ограничений без нарушений.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
