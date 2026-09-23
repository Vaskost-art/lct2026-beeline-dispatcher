"""Сценарии стресс-теста API: правки заявки, откат, сохранение, загрузка."""
from __future__ import annotations

import json

from stress_api_client import REGION, TIME_LIMIT, call, expect, fail, plan_is_valid
from stress_api_plan import Day


def adjustments(day: Day) -> None:
    some_order, engineers = day.some_order, day.engineers
    print("\n  Закрепление заявки и приоритет")
    expect("правка несуществующей заявки", "POST", "/api/order/adjust", (404,),
           body={"region": REGION, "order_id": "НЕТ-ТАКОЙ", "set_lock": True,
                 "lock_to": engineers[0]}, must_explain=True)
    expect("закрепление за призраком", "POST", "/api/order/adjust", (404,),
           body={"region": REGION, "order_id": some_order, "set_lock": True,
                 "lock_to": "Бригада Призрак"}, must_explain=True)
    expect("приоритет не из справочника", "POST", "/api/order/adjust", (422,),
           body={"region": REGION, "order_id": some_order,
                 "priority": "Как получится"})
    expect("пустая правка", "POST", "/api/order/adjust", (200,),
           body={"region": REGION, "order_id": some_order})
    plan_is_valid("после пустой правки")

    status, adjusted = call("POST", "/api/order/adjust",
                            {"region": REGION, "order_id": some_order,
                             "priority": "Срочная", "time_limit_sec": TIME_LIMIT})
    if status == 200:
        got = next((o["priority"] for o in adjusted["orders"]
                    if o["id"] == some_order), None)
        if got not in ("Срочная",):
            fail("смена приоритета", f"приоритет остался «{got}»")
        plan_is_valid("после смены приоритета")

    # закрепляем за тем, кто заявку действительно может взять
    lock_target = None
    for engineer in adjusted.get("engineers", []) if status == 200 else []:
        order_row = next((o for o in adjusted["orders"] if o["id"] == some_order), None)
        if not order_row:
            break
        if (order_row["required_skill"] in engineer["skills"]
                and (not order_row["required_vehicle"]
                     or order_row["required_vehicle"] == engineer["vehicle"])):
            lock_target = engineer["id"]
            break
    if lock_target:
        status, locked_plan = call("POST", "/api/order/adjust",
                                   {"region": REGION, "order_id": some_order,
                                    "set_lock": True, "lock_to": lock_target,
                                    "time_limit_sec": TIME_LIMIT})
        if status == 200:
            holder = next((r["engineer_id"] for r in locked_plan["routes"]
                           for st in r["stops"] if st["order_id"] == some_order), None)
            if holder is not None and holder != lock_target:
                fail("закрепление", f"заявка ушла к «{holder}» вместо «{lock_target}»")
            plan_is_valid("после закрепления")


def undo_and_save() -> None:
    print("\n  Шаг назад")
    for step in range(3):
        status, _ = call("POST", "/api/undo", {"region": REGION})
        if status not in (200, 409):
            fail("шаг назад", f"неожиданный код {status}")
        plan_is_valid(f"после отката {step + 1}")
    expect("откат по несуществующему району", "POST", "/api/undo", (404, 409),
           body={"region": "нет-такого"}, must_explain=True)

    print("\n  Сохранение и восстановление дня")
    expect("сохранение несуществующего района", "POST", "/api/plan/save", (404, 409),
           body={"region": "нет-такого"}, must_explain=True)
    expect("что сохранено по пустому району", "GET",
           "/api/plan/saved/нет-такого", (200,))
    expect("восстановление без сохранения", "POST", "/api/plan/restore", (404,),
           body={"region": "нет-такого"}, must_explain=True)
    status, saved = call("POST", "/api/plan/save", {"region": REGION})
    if status != 200:
        fail("сохранение дня", f"код {status}")
    else:
        status, before = call("GET", f"/api/plan/{REGION}")
        status, restored = call("POST", "/api/plan/restore", {"region": REGION})
        if status != 200:
            fail("восстановление дня", f"код {status}")
        else:
            for key in ("orders_assigned", "used_engineers"):
                if before["metrics"][key] != restored["metrics"][key]:
                    fail("восстановление дня",
                         f"«{key}» разошлось: {before['metrics'][key]} -> "
                         f"{restored['metrics'][key]}")
            if abs(before["metrics"]["total_km"]
                   - restored["metrics"]["total_km"]) > 0.01:
                fail("восстановление дня", "пробег разошёлся после загрузки")
            plan_is_valid("после восстановления дня")


def risk_upload_export() -> None:
    print("\n  Прогноз опозданий на границах")
    expect("отрицательная просадка", "GET", f"/api/risk/{REGION}?overrun=-100", (200,))
    expect("запредельная просадка", "GET", f"/api/risk/{REGION}?overrun=999999", (200,))
    expect("нулевая просадка", "GET", f"/api/risk/{REGION}?overrun=0", (200,))
    expect("просадка не число", "GET", f"/api/risk/{REGION}?overrun=много", (422,))

    print("\n  Загрузка наборов данных")
    expect("пустой файл", "POST", "/api/dataset/upload?filename=x.json", (400,),
           raw=b"", must_explain=True)
    expect("мусор вместо json", "POST", "/api/dataset/upload?filename=x.json", (400,),
           raw=b"\x00\x01\x02 not json at all", must_explain=True)
    expect("json без исполнителей", "POST", "/api/dataset/upload?filename=x.json",
           (400,), raw=json.dumps({"orders": [], "engineers": []}).encode(),
           must_explain=True)
    expect("окно наизнанку", "POST", "/api/dataset/upload?filename=x.json", (400,),
           raw=json.dumps({
               "orders": [{"id": "A", "lat": 55.7, "lon": 37.6, "duration_min": 60,
                           "window_start": "16:00", "window_end": "10:00",
                           "required_skill": "Локальные работы"}],
               "engineers": [{"id": "E", "lat": 55.7, "lon": 37.6,
                              "shift_start": "09:00", "shift_end": "18:00",
                              "skills": ["Локальные работы"]}]}).encode(),
           must_explain=True)
    expect("четыре навыка у исполнителя", "POST",
           "/api/dataset/upload?filename=x.json", (400,),
           raw=json.dumps({
               "orders": [{"id": "A", "lat": 55.7, "lon": 37.6, "duration_min": 60,
                           "window_start": "10:00", "window_end": "12:00",
                           "required_skill": "Локальные работы"}],
               "engineers": [{"id": "E", "lat": 55.7, "lon": 37.6,
                              "shift_start": "09:00", "shift_end": "18:00",
                              "skills": ["Локальные работы", "Аварийные работы",
                                         "Работы на подключение и дозаказы",
                                         "Лишний навык"]}]}).encode(),
           must_explain=True)
    # Сервис отказывает по заголовку длины, не дочитывая тело, и клиент,
    # который продолжает слать девять мегабайт, может увидеть обрыв (код 0)
    # вместо 413. Главное здесь другое: файл не принят, сервис жив.
    expect("файл больше восьми мегабайт", "POST",
           "/api/dataset/upload?filename=big.json", (413, 0),
           raw=b"[" + b"0," * (9 * 1024 * 1024 // 2) + b"0]")
    expect("сервис жив после большого файла", "GET", "/api/meta", (200,))
    expect("csv без колонки «Заявка»", "POST", "/api/dataset/upload?filename=x.csv",
           (400,), raw="Имя;Адрес\nИванов;Москва\n".encode("cp1251"),
           must_explain=True)
    plan_is_valid("после неудачных загрузок")

    print("\n  Выгрузки")
    expect("план в формате ТЗ", "GET", f"/api/export/{REGION}", (200,))
    expect("набор данных", "GET", f"/api/dataset/{REGION}", (200,))
    expect("набор несуществующего района", "GET", "/api/dataset/нет-такого", (404,),
           must_explain=True)
