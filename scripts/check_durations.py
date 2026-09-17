#!/usr/bin/env python3
"""Проверка нормативов длительности по контрольному распределению.

Длительность работ — единственное число, взятое извне выгрузок. Проверить
его по данным можно: в контрольном распределении известно, какая бригада
какие заявки выполнила и в каких окнах. Для каждой бригады считается

    нужно времени = сумма длительностей её заявок + время в пути
    размах дня    = от начала первого окна до конца последнего

Если норматив систематически не влезает в размах, он завышен.

Чего этот скрипт НЕ делает: не выводит длительности из данных. Первая
версия пыталась — приравнивала «нужно времени» к размаху дня и решала
систему методом наименьших квадратов. Постановка оказалась неверной:
размах включает простои между окнами, и весь простой уходил в длительности.
Оценка получалась завышенной, загрузка Юго-востока доходила до 101%,
а планы становились хуже, чем у живого диспетчера. Данные дают верхнюю
границу, а не точное значение.

    python3 scripts/check_durations.py            # отчёт
    python3 scripts/check_durations.py --fit      # подобрать, не нарушая границу
    python3 scripts/check_durations.py --fit --apply

Подбор односторонний: он только опускает длительности тех типов работ,
из-за которых день бригады перестаёт помещаться в размах, и держится
за исходный норматив тем крепче, чем реже тип встречается.
"""
from __future__ import annotations

import argparse
import os
import re
import statistics
import sys
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from dispatcher.domain import norms  # noqa: E402
from dispatcher.domain.distance import road_km, travel_minutes  # noqa: E402
from dispatcher.infrastructure.ingest import REGIONS, load_scenario  # noqa: E402

RAW_DIR = os.path.join(ROOT, "data", "raw")
CACHE = os.path.join(ROOT, "data", "geo_cache.json")

DURATION_MIN = 20
DURATION_MAX = 240
MIN_SPAN_MIN = 4 * 60
PRIOR_STRENGTH = 6.0
ITERATIONS = 40000
LEARNING_RATE = 1e-4

# Допуск: день бригады считается вместившимся, если нужное время не превышает
# размах. Ровно 1.0 — без поблажки, факт есть факт.
TOLERANCE = 1.0


def collect():
    """Наблюдения «бригадо-день»: счётчики типов, время в пути, размах."""
    rows = []
    samples: dict[str, int] = defaultdict(int)
    for key in REGIONS:
        scenario = load_scenario(key, RAW_DIR, CACHE)
        crews: dict[str, list] = defaultdict(list)
        for order in scenario.orders:
            if order.control_engineer:
                crews[order.control_engineer].append(order)
        engineers = {e.id: e for e in scenario.engineers}

        for crew, orders in crews.items():
            engineer = engineers.get(crew)
            if engineer is None or len(orders) < 2:
                continue
            ordered = sorted(orders, key=lambda o: (o.window_start, o.window_end))
            span = (max(o.window_end for o in ordered)
                    - min(o.window_start for o in ordered))
            if span < MIN_SPAN_MIN:
                continue
            travel = 0
            lat, lon = engineer.lat, engineer.lon
            for order in ordered:
                travel += travel_minutes(
                    road_km(lat, lon, order.lat, order.lon), engineer.vehicle)
                lat, lon = order.lat, order.lon
            counts: dict[str, int] = defaultdict(int)
            for order in ordered:
                counts[order.type_hd] += 1
                samples[order.type_hd] += 1
            rows.append({"crew": crew, "region": scenario.region_name,
                         "counts": dict(counts), "travel": travel, "span": span,
                         "orders": len(ordered)})
    return rows, dict(samples)


def build_matrix(rows, types):
    matrix = np.zeros((len(rows), len(types)))
    travel = np.zeros(len(rows))
    span = np.zeros(len(rows))
    for i, row in enumerate(rows):
        for t, n in row["counts"].items():
            matrix[i, types.index(t)] = n
        travel[i] = row["travel"]
        span[i] = row["span"]
    return matrix, travel, span


def fit(matrix, travel, span, prior, counts):
    """Односторонний подбор: штрафуем только за выход за размах дня."""
    scale = max(float(np.abs(matrix).max()), 1.0)
    a = matrix / scale
    budget = (span * TOLERANCE - travel) / scale
    base = max(float(np.mean(np.diag(a.T @ a))), 1e-9)
    weights = PRIOR_STRENGTH * base / np.maximum(counts, 1.0)

    x = prior.copy().astype(float)
    for _ in range(ITERATIONS):
        excess = np.maximum(a @ x - budget, 0.0)
        gradient = 2 * (a.T @ excess) + 2 * weights * (x - prior)
        x = np.clip(x - LEARNING_RATE * gradient, DURATION_MIN, DURATION_MAX)
    return x


def report(rows, matrix, travel, span, durations, label):
    need = matrix @ durations + travel
    ratio = need / span
    over = int((ratio > TOLERANCE).sum())
    print(f"  {label}")
    print(f"     не помещаются в размах дня: {over} из {len(rows)} "
          f"({over / len(rows) * 100:.0f}%)")
    print(f"     отношение «нужно времени / размах»: "
          f"медиана {statistics.median(ratio):.2f}, "
          f"максимум {max(ratio):.2f}")
    return ratio


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fit", action="store_true",
                        help="подобрать длительности, не нарушая верхнюю границу")
    parser.add_argument("--apply", action="store_true",
                        help="записать подобранное в dispatcher/domain/norms.py")
    args = parser.parse_args()

    rows, samples = collect()
    types = sorted({t for row in rows for t in row["counts"]})
    matrix, travel, span = build_matrix(rows, types)
    prior = np.array([float(norms.DURATION_BY_TYPE_HD.get(t, norms.DEFAULT_DURATION))
                      for t in types])
    counts = np.array([float(samples.get(t, 0)) for t in types])

    print(f"Бригадо-дней в выборке: {len(rows)}, типов работ: {len(types)}\n")
    ratio = report(rows, matrix, travel, span, prior, "Текущий норматив:")

    worst = sorted(range(len(rows)), key=lambda i: -ratio[i])[:5]
    print("\n  Самые плотные дни:")
    for i in worst:
        row = rows[i]
        print(f"     {row['crew'][:26]:26s} {row['region'][:12]:12s} "
              f"{row['orders']:2d} заявок, размах {span[i] / 60:4.1f} ч, "
              f"нужно {(matrix[i] @ prior + travel[i]) / 60:4.1f} ч "
              f"({ratio[i]:.2f})")

    if not args.fit:
        print("\n  Вывод: если медиана заметно меньше единицы, норматив факту "
              "не противоречит,\n  а разница — реальные простои между окнами. "
              "Уточнить длительности по этим\n  данным нельзя: размах дня даёт "
              "только верхнюю границу.")
        print("\n  Подобрать длительности в пределах этой границы: --fit")
        return 0

    tuned = fit(matrix, travel, span, prior, counts)
    print()
    report(rows, matrix, travel, span, tuned, "После подбора:")

    print(f"\n{'Тип работ':42s} {'набл.':>6s} {'норматив':>9s} {'подбор':>8s}")
    print("-" * 70)
    result: dict[str, int] = {}
    for index in sorted(range(len(types)), key=lambda i: -counts[i]):
        value = int(round(tuned[index] / 5) * 5)
        result[types[index]] = value
        mark = "" if value == int(prior[index]) else f"  {value - int(prior[index]):+d}"
        print(f"{types[index][:42]:42s} {int(counts[index]):6d} "
              f"{int(prior[index]):9d} {value:8d}{mark}")

    if args.apply:
        path = os.path.join(ROOT, "src", "dispatcher", "domain", "norms.py")
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        block = "\n".join(f'    "{t}": {result[t]},'
                          for t in sorted(result, key=lambda x: -result[x]))
        source = re.sub(
            r"DURATION_BY_TYPE_HD = \{.*?\n\}",
            "DURATION_BY_TYPE_HD = {\n"
            "    # Проверено и подобрано по контрольному распределению\n"
            "    # скриптом scripts/check_durations.py.\n" + block + "\n}",
            source, count=1, flags=re.S)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(source)
        print(f"\nЗаписано в {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
