#!/usr/bin/env python3
"""Стресс-тест планировщика на вырожденных и граничных случаях.

Обычная самопроверка (`selftest.py`) прогоняет реальные данные. Здесь наоборот:
данные подбираются так, чтобы сломать алгоритм — пустой набор, окно короче
работы, смена длиной в минуту, все заявки в одной точке, никто не подходит
по навыку, событие до начала смены и после её конца.

После КАЖДОЙ операции проверяется один и тот же набор инвариантов. План,
который их нарушает, неверен, даже если программа не упала.

Запуск:  python3 scripts/stress.py
Код возврата 0 — все ветки прошли, 1 — есть нарушения.
"""
from __future__ import annotations

import os
import sys
import traceback
from dataclasses import replace

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from dispatcher.domain import (  # noqa: E402
    Engineer,
    Order,
    Plan,
    hhmm,
    norms,  # noqa: E402
)
from dispatcher.services.impact import plan_risk  # noqa: E402
from dispatcher.services.metrics import plan_metrics  # noqa: E402
from dispatcher.services.planning.baseline import solve_baseline, solve_greedy  # noqa: E402
from dispatcher.services.planning.optimizer import solve_optimized  # noqa: E402
from dispatcher.services.replanning.apply import replan  # noqa: E402
from dispatcher.services.replanning.events import (  # noqa: E402
    KIND_CANCEL,
    KIND_DELAYED,
    KIND_UNAVAILABLE,
    KIND_URGENT,
    ReplanEvent,
    make_urgent_order,
)
from dispatcher.services.replanning.repair import MODE_FULL, MODE_MINIMAL  # noqa: E402
from dispatcher.services.routing import evaluate_sequence  # noqa: E402
from dispatcher.services.validate import validate  # noqa: E402

TIME_LIMIT = int(os.environ.get("STRESS_TIME_LIMIT", "3"))

problems: list[str] = []
checks_done = 0


def fail(where: str, what: str) -> None:
    problems.append(f"{where}: {what}")
    print(f"      ✗ {what}")


# --------------------------------------------------------------------------
#  Инварианты — то, что обязано выполняться для ЛЮБОГО плана
# --------------------------------------------------------------------------

def check_invariants(where: str, plan: Plan, orders: list[Order],
                     engineers: list[Engineer]) -> None:
    global checks_done
    checks_done += 1

    order_ids = {o.id for o in orders}
    by_id = {o.id: o for o in orders}
    assigned: list[str] = []
    for route in plan.routes:
        assigned.extend(s.order_id for s in route.stops)

    # 1. Никаких дублей в назначениях
    if len(assigned) != len(set(assigned)):
        dupes = [x for x in set(assigned) if assigned.count(x) > 1]
        fail(where, f"заявка назначена дважды: {dupes[:3]}")

    # 2. Назначены только существующие заявки
    unknown = set(assigned) - order_ids
    if unknown:
        fail(where, f"назначены несуществующие заявки: {sorted(unknown)[:3]}")

    # 3. Назначенное и неназначенное не пересекаются
    unassigned_ids = {u.order_id for u in plan.unassigned}
    both = set(assigned) & unassigned_ids
    if both:
        fail(where, f"заявка одновременно назначена и не назначена: {sorted(both)[:3]}")

    # 4. Вместе они покрывают весь набор
    covered = set(assigned) | unassigned_ids
    if covered != order_ids:
        missing = order_ids - covered
        extra = covered - order_ids
        if missing:
            fail(where, f"заявки потерялись, их нет ни в плане, ни в отказах: "
                        f"{sorted(missing)[:3]}")
        if extra:
            fail(where, f"в отказах есть посторонние заявки: {sorted(extra)[:3]}")

    # 5. У каждого отказа есть причина словами
    for u in plan.unassigned:
        if not (u.reason_text or "").strip():
            fail(where, f"у заявки {u.order_id} отказ без причины")
            break
        if not (u.reason or "").strip():
            fail(where, f"у заявки {u.order_id} отказ без кода причины")
            break

    # 6. Времена внутри маршрута монотонны и неотрицательны
    for route in plan.routes:
        previous_end = None
        for stop in route.stops:
            if stop.start > stop.end:
                fail(where, f"{route.engineer_id}/{stop.order_id}: "
                            f"начало {hhmm(stop.start)} позже конца {hhmm(stop.end)}")
                break
            if stop.arrival > stop.start:
                fail(where, f"{route.engineer_id}/{stop.order_id}: "
                            f"работы начаты раньше прибытия")
                break
            if stop.travel_km < 0 or stop.travel_min < 0 or stop.wait_min < 0:
                fail(where, f"{route.engineer_id}/{stop.order_id}: "
                            f"отрицательные пробег, время в пути или ожидание")
                break
            if previous_end is not None and stop.arrival < previous_end:
                fail(where, f"{route.engineer_id}/{stop.order_id}: "
                            f"выехал раньше, чем закончил предыдущую заявку")
                break
            order = by_id.get(stop.order_id)
            if order and stop.end - stop.start != order.duration_min:
                fail(where, f"{route.engineer_id}/{stop.order_id}: "
                            f"длительность работ не совпадает с заявкой")
                break
            previous_end = stop.end

    # 7. Метрики не противоречат плану
    if plan.total_km < -1e-9:
        fail(where, "суммарный пробег отрицательный")
    if plan.used_engineers > len(engineers):
        fail(where, "задействовано больше исполнителей, чем есть")

    # 8. Независимый аудит ограничений
    report = validate(plan, orders, engineers)
    if not report.ok:
        first = report.violations[0]
        fail(where, f"аудит: {first.rule} — {first.text}")

    # 9. Метрики считаются без исключений
    try:
        plan_metrics(plan, orders, engineers)
    except Exception as exc:
        fail(where, f"метрики не посчитались: {exc}")

    # 10. Прогноз опозданий считается без исключений
    try:
        plan_risk(plan, orders, engineers)
    except Exception as exc:
        fail(where, f"прогноз опозданий не посчитался: {exc}")


# --------------------------------------------------------------------------
#  Конструкторы данных
# --------------------------------------------------------------------------

BASE_LAT, BASE_LON = 55.75, 37.62


def order(oid: str, *, lat: float = BASE_LAT, lon: float = BASE_LON,
          duration: int = 60, start: int = 10 * 60, end: int = 12 * 60,
          skill: str = norms.SKILL_LOCAL, vehicle: str | None = None,
          priority: str = norms.PRIORITY_NORMAL, district: str = "Тестовый") -> Order:
    return Order(id=oid, lat=lat, lon=lon, address=f"Адрес {oid}", district=district,
                 duration_min=duration, window_start=start, window_end=end,
                 priority=priority, required_skill=skill, required_vehicle=vehicle,
                 type_bk="Локальная заявка", type_hd="Нет линка")


def engineer(eid: str, *, lat: float = BASE_LAT, lon: float = BASE_LON,
             shift: tuple[int, int] = (9 * 60, 22 * 60),
             skills: list[str] | None = None,
             vehicle: str = norms.VEHICLE_CAR) -> Engineer:
    return Engineer(id=eid, name=eid, lat=lat, lon=lon,
                    start_address="База", shift_start=shift[0], shift_end=shift[1],
                    skills=skills or [norms.SKILL_LOCAL], vehicle=vehicle)


def case(name: str, orders: list[Order], engineers: list[Engineer]) -> tuple:
    return (name, orders, engineers)


def build_cases() -> list[tuple]:
    """Вырожденные и граничные наборы данных."""
    all_skills = list(dict.fromkeys(norms.SKILL_BY_TYPE_BK.values()))
    cases = [
        case("пустой набор", [], [engineer("E1")]),
        case("нет исполнителей", [order("O1")], []),
        case("пусто и там и там", [], []),
        case("одна заявка, один исполнитель", [order("O1")], [engineer("E1")]),

        case("все заявки в одной точке",
             [order(f"O{i}", duration=30) for i in range(1, 9)],
             [engineer("E1"), engineer("E2")]),

        case("заявки за сотни километров",
             [order("O1", lat=55.75, lon=37.62),
              order("O2", lat=54.84, lon=38.16, start=11 * 60, end=13 * 60),
              order("O3", lat=56.30, lon=36.70, start=12 * 60, end=14 * 60)],
             [engineer("E1")]),

        case("окно короче длительности работ",
             [order("O1", duration=180, start=10 * 60, end=10 * 60 + 30)],
             [engineer("E1")]),

        case("длительность больше смены",
             [order("O1", duration=900)],
             [engineer("E1", shift=(9 * 60, 18 * 60))]),

        case("смена длиной в минуту",
             [order("O1")],
             [engineer("E1", shift=(10 * 60, 10 * 60 + 1))]),

        case("круглосуточное окно",
             [order(f"O{i}", start=1, end=23 * 60 + 59) for i in range(1, 5)],
             [engineer("E1")]),

        case("окно ровно равно длительности",
             [order("O1", duration=120, start=10 * 60, end=12 * 60)],
             [engineer("E1")]),

        case("ни у кого нет нужного навыка",
             [order("O1", skill=norms.SKILL_EMERGENCY)],
             [engineer("E1", skills=[norms.SKILL_LOCAL])]),

        case("нужен автомобиль, все пешком",
             [order("O1", vehicle=norms.VEHICLE_CAR)],
             [engineer("E1", vehicle=norms.VEHICLE_FOOT)]),

        case("все заявки срочные",
             [order(f"O{i}", priority=norms.PRIORITY_URGENT,
                    lat=BASE_LAT + i * 0.01) for i in range(1, 11)],
             [engineer("E1"), engineer("E2")]),

        case("все заявки в одно окно, людей не хватает",
             [order(f"O{i}", duration=90, start=10 * 60, end=12 * 60,
                    lat=BASE_LAT + i * 0.02) for i in range(1, 13)],
             [engineer("E1")]),

        case("исполнителей больше, чем заявок",
             [order("O1")],
             [engineer(f"E{i}") for i in range(1, 16)]),

        case("три навыка у одного, по одному у прочих",
             [order(f"O{i}", skill=all_skills[i % 3], lat=BASE_LAT + i * 0.005)
              for i in range(1, 10)],
             [engineer("E-все", skills=all_skills)]
             + [engineer(f"E{i}", skills=[all_skills[i]]) for i in range(3)]),

        case("все типы транспорта",
             [order(f"O{i}", lat=BASE_LAT + i * 0.004) for i in range(1, 9)],
             [engineer(f"E-{v}", vehicle=v) for v in norms.SPEED_KMH]),

        case("смены не пересекаются с окнами",
             [order("O1", start=10 * 60, end=12 * 60)],
             [engineer("E1", shift=(18 * 60, 22 * 60))]),

        case("смена начинается после конца окна",
             [order("O1", start=8 * 60, end=9 * 60)],
             [engineer("E1", shift=(20 * 60, 23 * 60))]),

        case("координаты на экваторе и нулевом меридиане",
             [order("O1", lat=0.0, lon=0.0), order("O2", lat=0.01, lon=0.01)],
             [engineer("E1", lat=0.0, lon=0.0)]),

        case("отрицательные координаты",
             [order("O1", lat=-33.87, lon=-70.65),
              order("O2", lat=-33.88, lon=-70.66)],
             [engineer("E1", lat=-33.87, lon=-70.65)]),

        case("спецсимволы и юникод в идентификаторах",
             [order("O-1/2«тест»", district="Район «Северный»"),
              order("O\t2\n", district="Район 🚐")],
             [engineer("Бригада «Смирнов» & Co.")]),

        case("очень длинные строки",
             [order("O" + "1" * 300, district="Р" * 500)],
             [engineer("E" + "2" * 300)]),

        case("сто заявок, пятнадцать исполнителей",
             [order(f"O{i}", duration=45,
                    start=(9 + i % 12) * 60, end=(11 + i % 12) * 60,
                    lat=BASE_LAT + (i % 10) * 0.01, lon=BASE_LON + (i // 10) * 0.01,
                    skill=all_skills[i % 3],
                    priority=norms.PRIORITY_URGENT if i % 7 == 0
                             else norms.PRIORITY_NORMAL)
              for i in range(1, 101)],
             [engineer(f"E{i}", skills=all_skills[: 1 + i % 3],
                       vehicle=list(norms.SPEED_KMH)[i % 4],
                       shift=(8 * 60 + i * 10, 20 * 60 + i * 5))
              for i in range(1, 16)]),
    ]
    return cases


# --------------------------------------------------------------------------
#  Прогон
# --------------------------------------------------------------------------

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


def run_events(name: str, orders: list[Order], engineers: list[Engineer],
               plan: Plan) -> None:
    """Все ветки перепланирования, включая граничные моменты времени."""
    if not orders or not engineers:
        return

    assigned = [s.order_id for r in plan.routes for s in r.stops]
    any_order = assigned[0] if assigned else orders[0].id
    busiest = max(plan.routes, key=lambda r: len(r.stops)).engineer_id \
        if plan.routes else engineers[0].id
    idle = next((r.engineer_id for r in plan.routes if not r.stops), None)

    urgent = make_urgent_order(
        order_id="STRESS-URGENT", lat=orders[0].lat, lon=orders[0].lon,
        address="Проверочная точка", district=orders[0].district,
        duration_min=60, window_start=14 * 60, window_end=16 * 60,
        required_skill=orders[0].required_skill)

    urgent_past = replace(urgent, id="STRESS-PAST",
                          window_start=1, window_end=2)
    urgent_no_skill = replace(urgent, id="STRESS-NOSKILL",
                              required_skill=norms.SKILL_EMERGENCY,
                              required_vehicle=norms.VEHICLE_BIKE)

    events = [
        ("срочная днём", ReplanEvent(KIND_URGENT, 13 * 60, new_order=urgent)),
        ("срочная в 00:00", ReplanEvent(KIND_URGENT, 0, new_order=urgent)),
        ("срочная в 23:59", ReplanEvent(KIND_URGENT, 23 * 60 + 59, new_order=urgent)),
        ("срочная с окном в прошлом",
         ReplanEvent(KIND_URGENT, 13 * 60, new_order=urgent_past)),
        ("срочная, которую некому взять",
         ReplanEvent(KIND_URGENT, 13 * 60, new_order=urgent_no_skill)),
        ("отмена назначенной", ReplanEvent(KIND_CANCEL, 12 * 60, order_id=any_order)),
        ("отмена в 00:00", ReplanEvent(KIND_CANCEL, 0, order_id=orders[0].id)),
        ("отмена в 23:59",
         ReplanEvent(KIND_CANCEL, 23 * 60 + 59, order_id=orders[0].id)),
        ("выбыл загруженный", ReplanEvent(KIND_UNAVAILABLE, 13 * 60,
                                          engineer_id=busiest)),
        ("выбыл в 00:00", ReplanEvent(KIND_UNAVAILABLE, 0, engineer_id=busiest)),
        ("выбыл в 23:59", ReplanEvent(KIND_UNAVAILABLE, 23 * 60 + 59,
                                      engineer_id=busiest)),
    ]
    if idle:
        events.append(("выбыл незанятый",
                       ReplanEvent(KIND_UNAVAILABLE, 13 * 60, engineer_id=idle)))

    # Задержка бригады: от минимальной до заведомо съедающей весь день,
    # и на границах суток — там задержка либо не к чему применяться,
    # либо применяется к уже закрытой смене.
    events += [
        ("задержка 5 мин", ReplanEvent(KIND_DELAYED, 13 * 60,
                                       engineer_id=busiest, delay_min=5)),
        ("задержка 90 мин", ReplanEvent(KIND_DELAYED, 13 * 60,
                                        engineer_id=busiest, delay_min=90)),
        ("задержка на весь день", ReplanEvent(KIND_DELAYED, 13 * 60,
                                              engineer_id=busiest, delay_min=480)),
        ("задержка в 00:00", ReplanEvent(KIND_DELAYED, 0,
                                         engineer_id=busiest, delay_min=60)),
        ("задержка в 23:59", ReplanEvent(KIND_DELAYED, 23 * 60 + 59,
                                         engineer_id=busiest, delay_min=60)),
    ]
    if idle:
        events.append(("задержка незанятого",
                       ReplanEvent(KIND_DELAYED, 13 * 60,
                                   engineer_id=idle, delay_min=60)))

    for title, event in events:
        for mode in (MODE_MINIMAL, MODE_FULL):
            where = f"{name} / {title} / {mode}"
            try:
                result = replan(orders, engineers, plan, event, mode=mode,
                                time_limit_sec=TIME_LIMIT)
            except Exception as exc:
                fail(where, f"ИСКЛЮЧЕНИЕ {type(exc).__name__}: {exc}")
                traceback.print_exc()
                continue
            check_invariants(where, result.plan, result.orders, result.engineers)
            if not result.narrative:
                fail(where, "переплан не объяснил, что произошло")


def run_chain(name: str, orders: list[Order], engineers: list[Engineer],
              plan: Plan) -> None:
    """Цепочка событий: каждое следующее считается от применённого предыдущего."""
    if len(orders) < 3 or len(engineers) < 2:
        return
    current_orders, current_engineers, current = orders, engineers, plan
    for step in range(1, 6):
        assigned = [s.order_id for r in current.routes for s in r.stops]
        if not assigned:
            break
        event = ReplanEvent(KIND_CANCEL, (9 + step) * 60, order_id=assigned[0])
        where = f"{name} / цепочка, шаг {step}"
        try:
            result = replan(current_orders, current_engineers, current, event,
                            mode=MODE_MINIMAL, time_limit_sec=TIME_LIMIT)
        except Exception as exc:
            fail(where, f"ИСКЛЮЧЕНИЕ {type(exc).__name__}: {exc}")
            return
        check_invariants(where, result.plan, result.orders, result.engineers)
        current_orders, current_engineers, current = (
            result.orders, result.engineers, result.plan)


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
    print(f"Проверок инвариантов выполнено: {checks_done}")
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
