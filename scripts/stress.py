#!/usr/bin/env python3
"""Стресс-тест планировщика на вырожденных и граничных случаях.

Обычная самопроверка (`selftest.py`) прогоняет реальные данные. Здесь наоборот:
данные подбираются так, чтобы сломать алгоритм - пустой набор, окно короче
работы, смена длиной в минуту, все заявки в одной точке, никто не подходит
по навыку, событие до начала смены и после её конца.

После КАЖДОЙ операции проверяется один и тот же набор инвариантов. План,
который их нарушает, неверен, даже если программа не упала.

Запуск:  python3 scripts/stress.py
Код возврата 0 - все ветки прошли, 1 - есть нарушения.
"""
from __future__ import annotations

import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

import stress_checks  # noqa: E402
from stress_cases import build_cases  # noqa: E402
from stress_checks import TIME_LIMIT, check_invariants, fail  # noqa: E402
from stress_events import run_chain, run_events  # noqa: E402

from dispatcher.domain import Engineer, Order  # noqa: E402
from dispatcher.services.planning.baseline import solve_baseline, solve_greedy  # noqa: E402
from dispatcher.services.planning.optimizer import solve_optimized  # noqa: E402
from dispatcher.services.routing import evaluate_sequence  # noqa: E402

STRATEGIES = (
    ("без оптимизации", solve_baseline),
    ("быстрый расчёт", solve_greedy),
    ("оптимальный план", solve_optimized),
)


def run_solvers(name: str, orders: list[Order], engineers: list[Engineer]) -> dict:
    plans = {}
    for title, solver in STRATEGIES:
        where = f"{name} / {title}"
        try:
            plan = (solver(orders, engineers, time_limit_sec=TIME_LIMIT)
                    if solver is solve_optimized else solver(orders, engineers))
        except Exception as exc:
            fail(where, f"ИСКЛЮЧЕНИЕ {type(exc).__name__}: {exc}")
            traceback.print_exc()
            continue
        check_invariants(where, plan, orders, engineers)
        plans[title] = plan

    run_locks(name, orders, engineers)
    return plans


def run_locks(name: str, orders: list[Order], engineers: list[Engineer]) -> None:
    """Закрепление заявки за бригадой должно соблюдаться всеми способами счёта.

    Проверяем оба случая: закрепление за тем, кто заявку может взять
    (её обязаны отдать именно ему либо не назначить вовсе), и за тем,
    кто не может (её не должно оказаться ни у кого).
    """
    if not orders or not engineers:
        return

    target = orders[0]
    able = next((e for e in engineers if e.can_do(target)), None)
    unable = next((e for e in engineers if not e.can_do(target)), None)

    cases = []
    if able is not None:
        cases.append(("закреплена за подходящим", able.id, True))
    if unable is not None:
        cases.append(("закреплена за неподходящим", unable.id, False))

    for title, engineer_id, feasible in cases:
        locked = {target.id: engineer_id}
        for solver_title, solver in STRATEGIES:
            where = f"{name} / {title} / {solver_title}"
            try:
                plan = (solver(orders, engineers, time_limit_sec=TIME_LIMIT,
                               locked=locked)
                        if solver is solve_optimized
                        else solver(orders, engineers, locked=locked))
            except Exception as exc:
                fail(where, f"ИСКЛЮЧЕНИЕ {type(exc).__name__}: {exc}")
                traceback.print_exc()
                continue
            check_invariants(where, plan, orders, engineers)
            holder = next((r.engineer_id for r in plan.routes
                           for s in r.stops if s.order_id == target.id), None)
            if holder is not None and holder != engineer_id:
                fail(where, f"закреплённая заявка ушла к «{holder}» "
                            f"вместо «{engineer_id}»")
            if not feasible and holder is not None:
                fail(where, "заявка закреплена за тем, кто её не может взять, "
                            "но всё равно оказалась в плане")
    return


def run_sequences(name: str, orders: list[Order], engineers: list[Engineer]) -> None:
    """Ручная сборка маршрута: любая последовательность либо честно
    просчитана, либо честно отвергнута, но не принята молча."""
    if not orders or not engineers:
        return
    eng = engineers[0]
    for size in (1, 2, len(orders)):
        sequence = orders[:size]
        try:
            route, reason = evaluate_sequence(eng, sequence)
        except Exception as exc:
            fail(f"{name} / последовательность из {size}",
                 f"ИСКЛЮЧЕНИЕ {type(exc).__name__}: {exc}")
            continue
        if route is None and not reason:
            fail(f"{name} / последовательность из {size}",
                 "маршрут отвергнут без причины")
        if route is not None and len(route.stops) != len(sequence):
            fail(f"{name} / последовательность из {size}",
                 "в маршруте оказалось не столько визитов, сколько заявок")


def main() -> int:
    cases = build_cases()
    print(f"Вырожденных наборов: {len(cases)}, "
          f"лимит расчёта {TIME_LIMIT} с\n")

    for name, orders, engineers in cases:
        print(f"  {name}: {len(orders)} заявок, {len(engineers)} исполнителей")
        plans = run_solvers(name, orders, engineers)
        run_sequences(name, orders, engineers)
        best = plans.get("оптимальный план")
        if best is not None:
            run_events(name, orders, engineers, best)
            run_chain(name, orders, engineers, best)

    print()
    print("=" * 74)
    print(f"Проверок инвариантов выполнено: {stress_checks.checks_done}")
    problems = stress_checks.problems
    if problems:
        print(f"НАЙДЕНО НАРУШЕНИЙ: {len(problems)}\n")
        for item in problems[:40]:
            print(f"  · {item}")
        if len(problems) > 40:
            print(f"  …и ещё {len(problems) - 40}")
        return 1
    print("Нарушений нет: на всех ветках план остаётся корректным.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
