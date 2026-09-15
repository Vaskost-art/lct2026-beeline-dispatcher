#!/usr/bin/env python3
"""Собирает эталонный тестовый набор данных (ТЗ п. 6).

ТЗ требует набор на один рабочий день: 10–15 инженеров, не более 100 заявок,
и чтобы по нему можно было проверить все обязательные ограничения — в данных
должны встречаться все три навыка, разные комбинации навыков у исполнителей,
все типы транспорта, пересекающиеся временные окна и хотя бы один конфликт,
при котором простое последовательное распределение даёт менее эффективный план.

Набор не выдуман: он собран из реальной обезличенной выгрузки района Восток,
поэтому окна, адреса и состав работ настоящие. Скрипт заодно проверяет, что
все требования ТЗ к тестовому набору действительно выполнены, и печатает отчёт.

Запуск:  python3 scripts/make_sample.py
Результат: data/sample/{dataset.json, event.json, expected_result.json}
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))

import norms                                                    # noqa: E402
from dataset import order_to_json, scenario_to_json             # noqa: E402
from domain import hhmm                                         # noqa: E402
from ingest import load_scenario                                # noqa: E402
from metrics import plan_metrics                                # noqa: E402
from replan import KIND_URGENT, make_urgent_order               # noqa: E402
from solver import solve_baseline, solve_optimized              # noqa: E402
from validate import validate                                   # noqa: E402

RAW_DIR = os.path.join(ROOT, "data", "raw")
CACHE = os.path.join(ROOT, "data", "geo_cache.json")
OUT_DIR = os.path.join(ROOT, "data", "sample")

SOURCE_REGION = "vostok"
SAMPLE_NAME = "Демонстрационный набор: один рабочий день, район Восток"
TIME_LIMIT = 15


def build_event(scenario) -> dict:
    """Одно событие перепланирования: срочная авария в середине дня.

    Точка взята рядом с уже существующими заявками района, окно — дневное,
    чтобы событие имело смысл при любом плане.
    """
    anchor = next(o for o in scenario.orders if o.district == "Кузьминки")
    urgent = make_urgent_order(
        order_id="URGENT-001",
        lat=round(anchor.lat + 0.004, 6),
        lon=round(anchor.lon + 0.006, 6),
        address="Москва, ул.Юных Ленинцев, д. 5",
        district=anchor.district,
        duration_min=60,
        window_start=15 * 60,
        window_end=17 * 60,
        required_skill=norms.SKILL_EMERGENCY,
    )
    return {
        "kind": KIND_URGENT,
        "at": "13:30",
        "description": "В 13:30 поступила срочная авария в Кузьминках: "
                       "окно 15:00–17:00, час работ, нужен аварийный навык.",
        "new_order": order_to_json(urgent),
    }


def coverage_report(scenario) -> tuple[list[tuple[str, bool, str]], bool]:
    """Проверяет требования ТЗ к тестовому набору."""
    orders, engineers = scenario.orders, scenario.engineers

    skills_in_orders = {o.required_skill for o in orders}
    all_skills = set(dict.fromkeys(norms.SKILL_BY_TYPE_BK.values()))
    combos = {tuple(sorted(e.skills)) for e in engineers}
    vehicles = {e.vehicle for e in engineers}
    all_vehicles = set(norms.SPEED_KMH)

    # пересекающиеся окна: есть ли хотя бы одна пара заявок с общим интервалом
    overlapping = 0
    ordered = sorted(orders, key=lambda o: o.window_start)
    for i, a in enumerate(ordered):
        for b in ordered[i + 1:]:
            if b.window_start >= a.window_end:
                break
            overlapping += 1
    checks = [
        ("Все три навыка встречаются в заявках",
         skills_in_orders == all_skills,
         ", ".join(sorted(skills_in_orders))),
        ("Разные комбинации навыков у исполнителей",
         len(combos) >= 2,
         f"{len(combos)} различных комбинаций, размеры "
         f"{sorted({len(c) for c in combos})}"),
        ("От 1 до 3 навыков у каждого исполнителя",
         all(1 <= len(e.skills) <= 3 for e in engineers),
         f"минимум {min(len(e.skills) for e in engineers)}, "
         f"максимум {max(len(e.skills) for e in engineers)}"),
        ("Встречаются все типы транспорта",
         vehicles == all_vehicles,
         ", ".join(sorted(vehicles))),
        ("Есть заявки с требованием типа транспорта",
         any(o.required_vehicle for o in orders),
         f"{sum(1 for o in orders if o.required_vehicle)} заявок"),
        ("Есть срочные заявки",
         any(o.priority == norms.PRIORITY_URGENT for o in orders),
         f"{sum(1 for o in orders if o.priority == norms.PRIORITY_URGENT)} заявок"),
        ("Есть пересекающиеся временные окна",
         overlapping > 0,
         f"{overlapping} пересекающихся пар"),
        ("Инженеров от 10 до 15",
         10 <= len(engineers) <= 15,
         f"{len(engineers)}"),
        ("Заявок не более 100",
         len(orders) <= 100,
         f"{len(orders)}"),
    ]
    return checks, all(ok for _, ok, _ in checks)


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    scenario = load_scenario(SOURCE_REGION, RAW_DIR, CACHE)
    scenario.region_name = SAMPLE_NAME

    event = build_event(scenario)

    # --- набор данных ---
    dataset = scenario_to_json(scenario, [event])
    dataset["meta"]["source"] = (
        "Собран из обезличенной выгрузки организаторов по району Восток "
        "за 17.08.2026. Поля, которых нет в выгрузке (длительность, навыки, "
        "транспорт, смены, стартовые точки), достроены по правилам из "
        "backend/norms.py — они описаны в README."
    )
    with open(os.path.join(OUT_DIR, "dataset.json"), "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=1)

    # --- событие отдельным файлом ---
    with open(os.path.join(OUT_DIR, "event.json"), "w", encoding="utf-8") as f:
        json.dump(event, f, ensure_ascii=False, indent=1)

    # --- пример ожидаемого формата результата ---
    plan = solve_optimized(scenario.orders, scenario.engineers,
                           time_limit_sec=TIME_LIMIT)
    metrics = plan_metrics(plan, scenario.orders, scenario.engineers)
    by_id = scenario.order_by_id
    assignment = {s.order_id: r.engineer_id
                  for r in plan.routes for s in r.stops}

    result = {
        "район": scenario.region_name,
        "стратегия": plan.strategy,
        "исполнители": [
            {
                "исполнитель": route.engineer_id,
                "пробег_км": round(route.total_km, 2),
                "время_в_пути_мин": route.total_travel_min,
                "маршрут": [
                    {
                        "порядок": i + 1,
                        "заявка": stop.order_id,
                        "адрес": by_id[stop.order_id].address,
                        "прибытие": hhmm(stop.arrival),
                        "начало_работ": hhmm(stop.start),
                        "окончание": hhmm(stop.end),
                        "пробег_до_точки_км": round(stop.travel_km, 2),
                    }
                    for i, stop in enumerate(route.stops)
                ],
            }
            for route in plan.routes if route.is_used
        ],
        "заявки": [
            {"заявка": o.id, "исполнитель": assignment.get(o.id),
             "статус": "назначена" if o.id in assignment else "не назначена"}
            for o in scenario.orders
        ],
        "не_назначены": [
            {"заявка": u.order_id, "причина": u.reason_text}
            for u in plan.unassigned
        ],
        "метрики": {
            "задействовано_исполнителей": metrics["used_engineers"],
            "доступно_исполнителей": metrics["engineers_available"],
            "пробег_по_исполнителям": {row["engineer_id"]: row["km"]
                                       for row in metrics["km_per_engineer"]},
            "суммарный_пробег_км": metrics["total_km"],
            "назначено_заявок": metrics["orders_assigned"],
            "всего_заявок": metrics["orders_total"],
        },
    }
    with open(os.path.join(OUT_DIR, "expected_result.json"), "w",
              encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)

    # --- отчёт о покрытии требований ТЗ ---
    print(f"Набор собран: {len(scenario.orders)} заявок, "
          f"{len(scenario.engineers)} исполнителей\n")
    print("Проверка требований ТЗ к тестовому набору (п. 6):")
    checks, ok = coverage_report(scenario)
    for title, passed, detail in checks:
        print(f"  [{'x' if passed else ' '}] {title}: {detail}")

    baseline = solve_baseline(scenario.orders, scenario.engineers)
    base_metrics = plan_metrics(baseline, scenario.orders, scenario.engineers)
    conflict = (base_metrics["orders_assigned"] < metrics["orders_assigned"]
                or base_metrics["avg_km_per_order"] > metrics["avg_km_per_order"])
    print(f"  [{'x' if conflict else ' '}] Последовательное распределение даёт "
          f"менее эффективный план: базовый вариант "
          f"{base_metrics['orders_assigned']}/{base_metrics['orders_total']} заявок "
          f"и {base_metrics['avg_km_per_order']:.2f} км на заявку против "
          f"{metrics['orders_assigned']}/{metrics['orders_total']} и "
          f"{metrics['avg_km_per_order']:.2f} км у оптимизатора")

    report = validate(plan, scenario.orders, scenario.engineers)
    print(f"  [{'x' if report.ok else ' '}] Пример результата проходит проверку "
          f"ограничений: {'нарушений нет' if report.ok else report.by_rule()}")

    print(f"\nФайлы записаны в {OUT_DIR}:")
    for name in ("dataset.json", "event.json", "expected_result.json"):
        size = os.path.getsize(os.path.join(OUT_DIR, name))
        print(f"  {name} — {size / 1024:.1f} КБ")

    return 0 if (ok and conflict and report.ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
