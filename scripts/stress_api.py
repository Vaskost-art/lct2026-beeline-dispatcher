#!/usr/bin/env python3
"""Стресс-тест HTTP-интерфейса: битые запросы и нарушенный порядок вызовов.

Проверяется не «работает ли счастливый путь» — это делают selftest.py и
stress.py, — а то, что сервис на любое кривое обращение отвечает понятным
кодом и текстом, а не пятисоткой и не молчаливым согласием.

Отдельно проверяется главный инвариант: после ЛЮБОЙ последовательности
вызовов текущий план остаётся допустимым по встроенному аудиту.

    python3 -m uvicorn app:app --port 8000    # в каталоге backend
    python3 scripts/stress_api.py             # в другом терминале

Код возврата 0 — все ветки ответили как ожидалось.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("STRESS_API_URL", "http://127.0.0.1:8000").rstrip("/")
REGION = "vostok"
TIME_LIMIT = int(os.environ.get("STRESS_TIME_LIMIT", "3"))

problems: list[str] = []
done = 0


def fail(label: str, what: str) -> None:
    """Отмечает провал проверки, у которой нет готового кода ответа."""
    global done
    done += 1
    problems.append(f"{label}: {what}")
    print(f"    ✗ {label}: {what}")


def unwrap(payload: object) -> object:
    """Разворачивает конверт {ok, data} либо {ok, error}.

    Проверки написаны про содержимое ответа, а не про его упаковку, поэтому
    конверт снимается в одном месте. Текст отказа кладётся под ключ
    «detail»: проверки внятности объяснения читают именно его.
    """
    if not isinstance(payload, dict) or "ok" not in payload:
        return payload
    if payload.get("ok") is True:
        return payload.get("data")
    error = payload.get("error")
    if isinstance(error, dict):
        return {"detail": error.get("message", ""), "code": error.get("code", "")}
    return payload


def call(method: str, path: str, body=None, raw: bytes | None = None,
         content_type: str = "application/json") -> tuple[int, object]:
    data = raw if raw is not None else (
        json.dumps(body, ensure_ascii=False).encode() if body is not None else None)
    safe_path = urllib.parse.quote(path, safe="/?=&%")
    request = urllib.request.Request(f"{BASE}{safe_path}", data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            text = response.read().decode("utf-8", "replace")
            return response.status, unwrap(json.loads(text) if text else None)
    except urllib.error.HTTPError as error:
        text = error.read().decode("utf-8", "replace")
        try:
            return error.code, unwrap(json.loads(text))
        except json.JSONDecodeError:
            return error.code, text
    except Exception as error:                      # сервис не поднят, таймаут
        return 0, str(error)


def expect(label: str, method: str, path: str, codes: tuple[int, ...],
           body=None, raw: bytes | None = None,
           must_explain: bool = False) -> object:
    """Проверяет код ответа и, где это важно, наличие внятного объяснения."""
    global done
    done += 1
    status, payload = call(method, path, body=body, raw=raw)
    if status not in codes:
        problems.append(
            f"{label}: ожидали {', '.join(map(str, codes))}, получили {status} "
            f"({str(payload)[:120]})")
        print(f"    ✗ {label}: {status}")
        return payload

    if must_explain:
        detail = payload.get("detail") if isinstance(payload, dict) else None
        if not isinstance(detail, (str, list)) or not str(detail).strip():
            problems.append(f"{label}: отказ без объяснения")
            print(f"    ✗ {label}: отказ без объяснения")
            return payload
        if isinstance(detail, str) and len(detail) < 12:
            problems.append(f"{label}: объяснение слишком куцее — «{detail}»")
            print(f"    ✗ {label}: куцее объяснение")
    print(f"    · {label}: {status}")
    return payload


def plan_is_valid(label: str) -> None:
    """Главный инвариант: текущий план всегда допустим."""
    global done
    done += 1
    status, payload = call("GET", f"/api/validate/{REGION}")
    if status != 200 or not isinstance(payload, dict):
        problems.append(f"{label}: аудит не ответил ({status})")
        print(f"    ✗ {label}: аудит не ответил")
        return
    if not payload.get("ok"):
        problems.append(f"{label}: план нарушает ограничения — {payload.get('by_rule')}")
        print(f"    ✗ {label}: план невалиден")
        return
    print(f"    · {label}: план допустим ({payload['checked_stops']} визитов)")


def main() -> int:
    global done
    status, meta = call("GET", "/api/meta")
    if status != 200:
        print(f"Сервис не отвечает на {BASE} — запустите его и повторите.")
        return 2
    print(f"Сервис на {BASE}, районов: {len(meta['regions'])}\n")

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
                        "time_limit_sec": TIME_LIMIT})
    plan_is_valid("после расчёта")

    assigned = [s["order_id"] for r in plan["routes"] for s in r["stops"]]
    unassigned = [u["order_id"] for u in plan["unassigned"]]
    engineers = [e["id"] for e in plan["engineers"]]
    some_order = assigned[0]

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
            done += 1
            if "не может" not in str(detail) and "не успевает" not in str(detail):
                problems.append("передача неподходящему: причина не названа")
            break
    if not refused:
        print("    · подходят все исполнители, отказ не воспроизвёлся")
    plan_is_valid("после ручных передач")

    expect("снять заявку с исполнителя", "POST", "/api/reassign", (200,),
           body={"region": REGION, "order_id": some_order, "engineer_id": None})
    plan_is_valid("после снятия заявки")

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
            "id": "STRESS-API-1", "lat": 55.74, "lon": 37.66,
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
           body={"region": REGION, "kind": "engineer_delayed", "at": "12:00"},
           must_explain=True)
    expect("задержка несуществующего", "POST", "/api/replan", (400,),
           body={"region": REGION, "kind": "engineer_delayed", "at": "12:00",
                 "engineer_id": "Бригада Призрак"}, must_explain=True)
    expect("задержка на ноль минут", "POST", "/api/replan", (422,),
           body={"region": REGION, "kind": "engineer_delayed", "at": "12:00",
                 "engineer_id": engineers[0], "delay_min": 0})
    expect("задержка на сутки", "POST", "/api/replan", (422,),
           body={"region": REGION, "kind": "engineer_delayed", "at": "12:00",
                 "engineer_id": engineers[0], "delay_min": 1440})
    for delay in (5, 90, 480):
        expect(f"задержка на {delay} мин", "POST", "/api/replan", (200,),
               body={"region": REGION, "kind": "engineer_delayed", "at": "12:00",
                     "engineer_id": engineers[0], "delay_min": delay,
                     "mode": "minimal", "apply": True,
                     "time_limit_sec": TIME_LIMIT})
        plan_is_valid(f"после задержки на {delay} мин")

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
    expect("файл больше восьми мегабайт", "POST",
           "/api/dataset/upload?filename=big.json", (413,),
           raw=b"[" + b"0," * (9 * 1024 * 1024 // 2) + b"0]", must_explain=True)
    expect("csv без колонки «Заявка»", "POST", "/api/dataset/upload?filename=x.csv",
           (400,), raw="Имя;Адрес\nИванов;Москва\n".encode("cp1251"),
           must_explain=True)
    plan_is_valid("после неудачных загрузок")

    print("\n  Выгрузки")
    expect("план в формате ТЗ", "GET", f"/api/export/{REGION}", (200,))
    expect("набор данных", "GET", f"/api/dataset/{REGION}", (200,))
    expect("набор несуществующего района", "GET", "/api/dataset/нет-такого", (404,),
           must_explain=True)

    print()
    print("=" * 74)
    print(f"Обращений к API проверено: {done}")
    if problems:
        print(f"НАЙДЕНО ОТКЛОНЕНИЙ: {len(problems)}\n")
        for item in problems:
            print(f"  · {item}")
        return 1
    print("Отклонений нет: на каждое кривое обращение сервис отвечает понятно, "
          "а план остаётся допустимым.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
