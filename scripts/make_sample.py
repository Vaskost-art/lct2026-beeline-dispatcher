#!/usr/bin/env python3
"""Собирает эталонный тестовый набор данных (ТЗ п. 6).

ТЗ требует набор на один рабочий день: 10-15 инженеров, не более 100 заявок,
и чтобы по нему можно было проверить все обязательные ограничения - в данных
должны встречаться все три навыка, разные комбинации навыков у исполнителей,
все типы транспорта, пересекающиеся временные окна и хотя бы один конфликт,
при котором простое последовательное распределение даёт менее эффективный план.

Набор собран из обезличенной синтетической выгрузки района Восток, окна и
адреса настоящие. Скрипт проверяет требования ТЗ к набору и ПЕРЕЗАПИСЫВАЕТ
data/sample/{dataset.json, event.json, expected_result.json}.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from sample_result import result_json  # noqa: E402

from dispatcher.domain import (  # noqa: E402
    catalog,
    norms,
)
from dispatcher.services.dataset import order_to_json, scenario_to_json  # noqa: E402
from dispatcher.services.metrics import plan_metrics  # noqa: E402
from dispatcher.services.planning.baseline import solve_baseline  # noqa: E402
from dispatcher.services.planning.costs import DEFAULT_TIME_LIMIT_SEC  # noqa: E402
from dispatcher.services.planning.optimizer import solve_optimized  # noqa: E402
from dispatcher.services.replanning.events import KIND_URGENT, make_new_order  # noqa: E402
from dispatcher.services.scenario import load_scenario  # noqa: E402
from dispatcher.services.validate import validate  # noqa: E402

RAW_DIR = os.path.join(ROOT, "data", "raw")
CACHE = os.path.join(ROOT, "data", "geo_cache.json")
OUT_DIR = os.path.join(ROOT, "data", "sample")

SOURCE_REGION = "vostok"
SAMPLE_NAME = "Демонстрационный набор: один рабочий день, район Восток"
#: Предохранитель как у сервиса: поиск останавливает счётный предел.
TIME_LIMIT = DEFAULT_TIME_LIMIT_SEC

#: ТЗ п. 6: в тестовом наборе 10-15 инженеров и все типы транспорта. Расчётный
#: минимум для Востока меньше, поэтому набор берёт нижнюю границу ТЗ, а одна
#: бригада без машины пересаживается на велосипед: в долях транспорта его нет.
SAMPLE_CREWS = 10


def build_event(scenario) -> dict:
    """Одно событие: авария в середине дня рядом с заявками района."""
    anchor = next(o for o in scenario.orders if o.district == "Кузьминки")
    urgent = make_new_order(
        order_id="URGENT-001",
        lat=round(anchor.lat + 0.004, 6),
        lon=round(anchor.lon + 0.006, 6),
        address="Москва, ул.Юных Ленинцев, д. 5",
        district=anchor.district,
        duration_min=60,
        window_start=15 * 60,
        window_end=17 * 60,
        required_skill=catalog.SKILL_EMERGENCY,
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
    all_vehicles = set(catalog.VEHICLES)

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
         any(o.priority == catalog.PRIORITY_URGENT for o in orders),
         f"{sum(1 for o in orders if o.priority == catalog.PRIORITY_URGENT)} заявок"),
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
    scenario = load_scenario(SOURCE_REGION, RAW_DIR, CACHE, crew_count=SAMPLE_CREWS)
    rider = next(crew for crew in reversed(scenario.engineers)
                 if crew.vehicle != catalog.VEHICLE_CAR)
    rider.vehicle = catalog.VEHICLE_BIKE
    scenario.region_name = SAMPLE_NAME

    event = build_event(scenario)

    # --- набор данных ---
    dataset = scenario_to_json(scenario, [event])
    dataset["meta"]["source"] = (
        "Собран из обезличенной выгрузки организаторов по району Восток "
        "за 17.08.2026. Поля, которых нет в выгрузке (длительность, навыки, "
        "транспорт, смены, стартовая точка), достроены по допущениям, "
        "описанным в README и в окне «Как считаем». По п. 6 ТЗ в наборе "
        f"{SAMPLE_CREWS} бригад и все типы транспорта, одна бригада на велосипеде."
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

    result = result_json(scenario, plan, metrics)
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
        print(f"  {name} - {size / 1024:.1f} КБ")

    return 0 if (ok and conflict and report.ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
