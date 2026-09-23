"""Сценарии стресс-теста API: справочники, расчёт, объяснения, события."""
from __future__ import annotations

import time
from dataclasses import dataclass

from stress_api_client import (
    REGION,
    TIME_LIMIT,
    call,
    expect,
    plan_is_valid,
    problems,
    tick,
)


@dataclass
class Day:
    """Что из построенного плана нужно следующим сценариям."""
    assigned: list[str]
    unassigned: list[str]
    engineers: list[str]
    some_order: str


def basics() -> None:
    print("  Справочники и сценарии")
    expect("meta", "GET", "/api/meta", (200,))
    expect("сценарий района", "GET", f"/api/scenario/{REGION}", (200,))
    expect("несуществующий район", "GET", "/api/scenario/нет-такого", (404,),
           must_explain=True)

    print("\n  Обращения до того, как план построен")
    expect("план до расчёта", "GET", "/api/plan/yugocentr", (409,), must_explain=True)
    expect("аудит до расчёта", "GET", "/api/validate/yugocentr", (409,),
           must_explain=True)
    expect("риски до расчёта", "GET", "/api/risk/yugocentr", (409,), must_explain=True)
    expect("выгрузка до расчёта", "GET", "/api/export/yugocentr", (409,),
           must_explain=True)
    expect("объяснение до расчёта", "POST", "/api/explain", (409,),
           body={"region": "yugocentr", "order_id": "X"}, must_explain=True)
    expect("переплан до расчёта", "POST", "/api/replan", (409,),
           body={"region": "yugocentr", "kind": "cancel_order", "order_id": "X"},
           must_explain=True)


def planning() -> Day:
    print("\n  Планирование")
    expect("несуществующий район", "POST", "/api/plan", (404,),
           body={"region": "нет-такого"}, must_explain=True)
    expect("неизвестная стратегия", "POST", "/api/plan", (422,),
           body={"region": REGION, "strategy": "магия"})
    expect("нулевой лимит времени", "POST", "/api/plan", (422,),
           body={"region": REGION, "time_limit_sec": 0})
    expect("запредельный лимит времени", "POST", "/api/plan", (422,),
           body={"region": REGION, "time_limit_sec": 100000})
    expect("без обязательного поля", "POST", "/api/plan", (422,), body={})

    plan = expect("нормальный расчёт", "POST", "/api/plan", (200,),
                  body={"region": REGION, "strategy": "optimized",
                        "time_limit_sec": TIME_LIMIT, "reset": True})
    plan_is_valid("после расчёта")

    assigned = [s["order_id"] for r in plan["routes"] for s in r["stops"]]
    unassigned = [u["order_id"] for u in plan["unassigned"]]
    engineers = [e["id"] for e in plan["engineers"]]
    some_order = assigned[0]
    return Day(assigned, unassigned, engineers, some_order)


def explain_and_reassign(day: Day) -> None:
    some_order, unassigned, engineers = day.some_order, day.unassigned, day.engineers
    print("\n  Объяснения")
    expect("объяснение назначенной", "POST", "/api/explain", (200,),
           body={"region": REGION, "order_id": some_order})
    if unassigned:
        expect("объяснение неназначенной", "POST", "/api/explain", (200,),
               body={"region": REGION, "order_id": unassigned[0]})
    expect("объяснение несуществующей", "POST", "/api/explain", (404,),
           body={"region": REGION, "order_id": "НЕТ-ТАКОЙ"}, must_explain=True)
    expect("пустой идентификатор", "POST", "/api/explain", (404, 422),
           body={"region": REGION, "order_id": ""})

    print("\n  Ручная передача заявки")
    expect("несуществующий исполнитель", "POST", "/api/reassign", (404,),
           body={"region": REGION, "order_id": some_order,
                 "engineer_id": "Бригада Призрак"}, must_explain=True)
    expect("несуществующая заявка", "POST", "/api/reassign", (404,),
           body={"region": REGION, "order_id": "НЕТ-ТАКОЙ",
                 "engineer_id": engineers[0]}, must_explain=True)
    # передача тому, кто заведомо не подходит: перебираем, пока не получим отказ
    refused = False
    for engineer_id in engineers:
        status, payload = call("POST", "/api/reassign",
                               {"region": REGION, "order_id": some_order,
                                "engineer_id": engineer_id})
        if status == 400:
            refused = True
            detail = payload.get("detail", "") if isinstance(payload, dict) else ""
            print(f"    · отказ с причиной: {str(detail)[:90]}")
            tick()
            if "не может" not in str(detail) and "не успевает" not in str(detail):
                problems.append("передача неподходящему: причина не названа")
            break
    if not refused:
        print("    · подходят все исполнители, отказ не воспроизвёлся")
    plan_is_valid("после ручных передач")

    expect("снять заявку с исполнителя", "POST", "/api/reassign", (200,),
           body={"region": REGION, "order_id": some_order, "engineer_id": None})
    plan_is_valid("после снятия заявки")


def replanning(day: Day) -> None:
    some_order, assigned, engineers = day.some_order, day.assigned, day.engineers
    print("\n  Перепланирование: кривые запросы")
    expect("неизвестный тип события", "POST", "/api/replan", (422,),
           body={"region": REGION, "kind": "конец_света"})
    expect("время события в кривом формате", "POST", "/api/replan", (400,),
           body={"region": REGION, "kind": "cancel_order",
                 "order_id": some_order, "at": "25:99"}, must_explain=True)
    expect("отмена несуществующей заявки", "POST", "/api/replan", (400,),
           body={"region": REGION, "kind": "cancel_order",
                 "order_id": "НЕТ-ТАКОЙ", "at": "12:00"}, must_explain=True)
    expect("выбытие несуществующего исполнителя", "POST", "/api/replan", (400,),
           body={"region": REGION, "kind": "engineer_unavailable",
                 "engineer_id": "Бригада Призрак", "at": "12:00"},
           must_explain=True)
    expect("срочная заявка без полей", "POST", "/api/replan", (400,),
           body={"region": REGION, "kind": "urgent_order", "at": "12:00"},
           must_explain=True)
    expect("срочная с занятым номером", "POST", "/api/replan", (400,),
           body={"region": REGION, "kind": "urgent_order", "at": "12:00",
                 "new_order": {"id": some_order, "lat": 55.75, "lon": 37.62,
                               "duration_min": 60, "window_start": "14:00",
                               "window_end": "16:00",
                               "required_skill": "Локальные работы"}},
           must_explain=True)
    expect("срочная с навыком не из справочника", "POST", "/api/replan", (400, 422),
           body={"region": REGION, "kind": "urgent_order", "at": "12:00",
                 "new_order": {"id": "NEW-1", "lat": 55.75, "lon": 37.62,
                               "duration_min": 60, "window_start": "14:00",
                               "window_end": "16:00",
                               "required_skill": "Телепортация"}},
           must_explain=True)
    plan_is_valid("после кривых запросов на переплан")

    print("\n  Перепланирование: применение подряд")
    for step, (kind, extra) in enumerate([
        ("cancel_order", {"order_id": assigned[1] if len(assigned) > 1 else some_order}),
        ("engineer_unavailable", {"engineer_id": engineers[0]}),
        ("urgent_order", {"new_order": {
            "id": f"STRESS-API-{int(time.time())}", "lat": 55.74, "lon": 37.66,
            "district": "Таганский", "address": "Проверочная точка",
            "duration_min": 60, "window_start": "15:00", "window_end": "17:00",
            "required_skill": "Локальные работы"}}),
    ], 1):
        body = {"region": REGION, "kind": kind, "at": f"1{step}:00",
                "mode": "minimal", "apply": True, "time_limit_sec": TIME_LIMIT}
        body.update(extra)
        expect(f"событие {step}: {kind}", "POST", "/api/replan", (200,), body=body)
        plan_is_valid(f"после события {step}")

    print("\n  Задержка бригады: границы")
    expect("задержка без исполнителя", "POST", "/api/replan", (400,),
           body={"region": REGION, "kind": "engineer_delayed", "at": "14:00"},
           must_explain=True)
    expect("задержка несуществующего", "POST", "/api/replan", (400,),
           body={"region": REGION, "kind": "engineer_delayed", "at": "14:00",
                 "engineer_id": "Бригада Призрак"}, must_explain=True)
    expect("задержка на ноль минут", "POST", "/api/replan", (422,),
           body={"region": REGION, "kind": "engineer_delayed", "at": "14:00",
                 "engineer_id": engineers[0], "delay_min": 0})
    expect("задержка на сутки", "POST", "/api/replan", (422,),
           body={"region": REGION, "kind": "engineer_delayed", "at": "14:00",
                 "engineer_id": engineers[0], "delay_min": 1440})
    for delay in (5, 90, 480):
        expect(f"задержка на {delay} мин", "POST", "/api/replan", (200,),
               body={"region": REGION, "kind": "engineer_delayed", "at": "14:00",
                     "engineer_id": engineers[0], "delay_min": delay,
                     "mode": "minimal", "apply": True,
                     "time_limit_sec": TIME_LIMIT})
        plan_is_valid(f"после задержки на {delay} мин")
