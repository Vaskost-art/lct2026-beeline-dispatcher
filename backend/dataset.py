"""Обмен наборами данных: чтение и запись в JSON, загрузка присланных файлов.

ТЗ п. 2.1: решение должно уметь загружать готовые тестовые данные из CSV или
JSON либо использовать встроенный демонстрационный набор. Поддержаны все три
источника:

  * встроенный набор — три выгрузки организаторов, читаются при старте;
  * CSV в формате организаторов — любая другая выгрузка того же вида;
  * JSON в формате этого модуля — полный набор с заявками, исполнителями
    и, при желании, событиями перепланирования.

Состав полей JSON соответствует таблице «Формат входных данных» из ТЗ п. 2.4:
у заявки — идентификатор, координаты и адрес, длительность, границы окна,
приоритет, требуемый навык и требуемый транспорт; у исполнителя — имя,
стартовая точка, границы смены, от одного до трёх навыков и тип транспорта;
у события — тип, время и предмет, а для срочной заявки — полный набор её полей.
Время везде «ЧЧ:ММ», длительность в минутах, координаты — широта и долгота.
"""
from __future__ import annotations

import json
from typing import Any

import norms
from domain import Engineer, Order, hhmm, parse_hhmm
from ingest import Scenario, decode_csv, parse_control_csv

FORMAT_VERSION = 1


class DatasetError(ValueError):
    """Ошибка разбора присланного набора данных, понятная пользователю."""


# --- запись -------------------------------------------------------------------

def order_to_json(order: Order) -> dict:
    data = {
        "id": order.id,
        "lat": round(order.lat, 6),
        "lon": round(order.lon, 6),
        "address": order.address,
        "district": order.district,
        "duration_min": order.duration_min,
        "window_start": hhmm(order.window_start),
        "window_end": hhmm(order.window_end),
        "priority": order.priority,
        "required_skill": order.required_skill,
        "required_vehicle": order.required_vehicle,
    }
    # справочные поля — не обязательны для планирования, но полезны в интерфейсе
    if order.type_bk:
        data["type_bk"] = order.type_bk
    if order.type_hd:
        data["type_hd"] = order.type_hd
    if order.control_engineer:
        data["control_engineer"] = order.control_engineer
    # Точность координат едет вместе с заявкой: иначе сохранённый день или
    # выгруженный набор начинают выглядеть точнее, чем есть на самом деле.
    if order.geocode_precision:
        data["geocode_precision"] = order.geocode_precision
    return data


def engineer_to_json(engineer: Engineer) -> dict:
    return {
        "id": engineer.id,
        "name": engineer.name,
        "lat": round(engineer.lat, 6),
        "lon": round(engineer.lon, 6),
        "start_address": engineer.start_address,
        "shift_start": hhmm(engineer.shift_start),
        "shift_end": hhmm(engineer.shift_end),
        "skills": list(engineer.skills),
        "vehicle": engineer.vehicle,
        "break_min": engineer.break_min,
    }


def scenario_to_json(scenario: Scenario, events: list[dict] | None = None) -> dict:
    return {
        "format_version": FORMAT_VERSION,
        "meta": {
            "key": scenario.region_key,
            "name": scenario.region_name,
            "orders": len(scenario.orders),
            "engineers": len(scenario.engineers),
            "units": {
                "time": "ЧЧ:ММ",
                "duration": "минуты",
                "distance": "километры",
                "coordinates": "широта/долгота (WGS84)",
            },
            "reference_books": {
                "skills": list(dict.fromkeys(norms.SKILL_BY_TYPE_BK.values())),
                "vehicles": list(norms.SPEED_KMH.keys()),
                "priorities": [norms.PRIORITY_NORMAL, norms.PRIORITY_URGENT],
            },
        },
        "orders": [order_to_json(o) for o in scenario.orders],
        "engineers": [engineer_to_json(e) for e in scenario.engineers],
        "events": events or [],
    }


# --- чтение -------------------------------------------------------------------

def _require(data: dict, key: str, where: str) -> Any:
    if key not in data or data[key] in (None, ""):
        raise DatasetError(f"{where}: не заполнено обязательное поле «{key}»")
    return data[key]


def _time(value: Any, where: str, key: str) -> int:
    """Принимает «ЧЧ:ММ» или число минут от полуночи."""
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return parse_hhmm(str(value))
    except (ValueError, AttributeError):
        raise DatasetError(
            f"{where}: поле «{key}» должно быть временем в формате ЧЧ:ММ, "
            f"получено «{value}»")


def _coords(data: dict, where: str) -> tuple[float, float]:
    try:
        return float(_require(data, "lat", where)), float(_require(data, "lon", where))
    except (TypeError, ValueError):
        raise DatasetError(f"{where}: координаты «lat» и «lon» должны быть числами")


def order_from_json(data: dict) -> Order:
    order_id = str(_require(data, "id", "Заявка"))
    where = f"Заявка {order_id}"
    lat, lon = _coords(data, where)

    skill = str(data.get("required_skill") or norms.SKILL_LOCAL)
    if skill not in norms.SKILL_BY_TYPE_BK.values():
        raise DatasetError(
            f"{where}: навык «{skill}» отсутствует в справочнике. "
            f"Допустимы: {', '.join(dict.fromkeys(norms.SKILL_BY_TYPE_BK.values()))}")

    vehicle = data.get("required_vehicle") or None
    if vehicle and vehicle not in norms.SPEED_KMH:
        raise DatasetError(
            f"{where}: транспорт «{vehicle}» отсутствует в справочнике. "
            f"Допустимы: {', '.join(norms.SPEED_KMH)}")

    priority = str(data.get("priority") or norms.PRIORITY_NORMAL)
    if priority not in (norms.PRIORITY_NORMAL, norms.PRIORITY_URGENT):
        raise DatasetError(
            f"{where}: приоритет «{priority}» отсутствует в справочнике. "
            f"Допустимы: {norms.PRIORITY_NORMAL}, {norms.PRIORITY_URGENT}")

    try:
        duration = int(_require(data, "duration_min", where))
    except (TypeError, ValueError):
        raise DatasetError(f"{where}: «duration_min» должно быть числом минут")
    if duration <= 0:
        raise DatasetError(f"{where}: длительность работ должна быть больше нуля")

    window_start = _time(_require(data, "window_start", where), where, "window_start")
    window_end = _time(_require(data, "window_end", where), where, "window_end")
    if window_end <= window_start:
        raise DatasetError(
            f"{where}: конец временного окна ({hhmm(window_end)}) не позже "
            f"его начала ({hhmm(window_start)})")

    return Order(
        id=order_id, lat=lat, lon=lon,
        address=str(data.get("address") or ""),
        district=str(data.get("district") or ""),
        duration_min=duration,
        window_start=window_start, window_end=window_end,
        priority=priority, required_skill=skill, required_vehicle=vehicle,
        type_bk=str(data.get("type_bk") or ""),
        type_hd=str(data.get("type_hd") or ""),
        control_engineer=data.get("control_engineer") or None,
        geocode_precision=str(data.get("geocode_precision") or "provided"),
    )


def engineer_from_json(data: dict, allow_empty_shift: bool = False) -> Engineer:
    engineer_id = str(_require(data, "id", "Исполнитель"))
    where = f"Исполнитель {engineer_id}"
    lat, lon = _coords(data, where)

    skills = data.get("skills") or []
    if isinstance(skills, str):
        skills = [skills]
    skills = [str(s) for s in skills]
    if not 1 <= len(skills) <= 3:
        raise DatasetError(
            f"{where}: по ТЗ у исполнителя от одного до трёх навыков, "
            f"получено {len(skills)}")
    unknown = [s for s in skills if s not in norms.SKILL_BY_TYPE_BK.values()]
    if unknown:
        raise DatasetError(
            f"{where}: навыки {', '.join(unknown)} отсутствуют в справочнике")

    vehicle = str(data.get("vehicle") or norms.VEHICLE_CAR)
    if vehicle not in norms.SPEED_KMH:
        raise DatasetError(
            f"{where}: транспорт «{vehicle}» отсутствует в справочнике. "
            f"Допустимы: {', '.join(norms.SPEED_KMH)}")

    shift_start = _time(_require(data, "shift_start", where), where, "shift_start")
    shift_end = _time(_require(data, "shift_end", where), where, "shift_end")
    if shift_end < shift_start:
        raise DatasetError(
            f"{where}: конец смены ({hhmm(shift_end)}) раньше "
            f"её начала ({hhmm(shift_start)})")
    # Смена нулевой длины — не опечатка, а состояние: так выглядит бригада,
    # выбывшая в течение дня. В присланном наборе данных это почти наверняка
    # ошибка, поэтому там она запрещена, а при чтении сохранённого дня —
    # разрешена явным флагом.
    if shift_end == shift_start and not allow_empty_shift:
        raise DatasetError(
            f"{where}: смена нулевой длины ({hhmm(shift_start)}) — "
            f"исполнитель не сможет взять ни одной заявки")

    try:
        break_min = int(data.get("break_min") or 0)
    except (TypeError, ValueError):
        raise DatasetError(f"{where}: «break_min» должно быть числом минут")
    if break_min < 0 or break_min >= max(1, shift_end - shift_start):
        if not (allow_empty_shift and shift_end == shift_start and break_min == 0):
            raise DatasetError(
                f"{where}: перерыв {break_min} мин не помещается в смену "
                f"{hhmm(shift_start)}–{hhmm(shift_end)}")

    return Engineer(
        id=engineer_id, name=str(data.get("name") or engineer_id),
        lat=lat, lon=lon,
        start_address=str(data.get("start_address") or ""),
        shift_start=shift_start, shift_end=shift_end,
        skills=skills, vehicle=vehicle, break_min=break_min,
    )


def scenario_from_json(data: dict, region_key: str,
                       region_name: str | None = None) -> tuple[Scenario, list[dict]]:
    if not isinstance(data, dict):
        raise DatasetError("Ожидался объект JSON с полями «orders» и «engineers»")

    raw_orders = data.get("orders")
    raw_engineers = data.get("engineers")
    if not isinstance(raw_orders, list) or not raw_orders:
        raise DatasetError("В наборе нет списка заявок «orders»")
    if not isinstance(raw_engineers, list) or not raw_engineers:
        raise DatasetError("В наборе нет списка исполнителей «engineers»")

    orders: list[Order] = []
    seen: set[str] = set()
    for item in raw_orders:
        order = order_from_json(item)
        if order.id in seen:
            raise DatasetError(f"Заявка {order.id} встречается в наборе дважды")
        seen.add(order.id)
        orders.append(order)

    engineers: list[Engineer] = []
    seen_engineers: set[str] = set()
    for item in raw_engineers:
        engineer = engineer_from_json(item)
        if engineer.id in seen_engineers:
            raise DatasetError(f"Исполнитель {engineer.id} встречается дважды")
        seen_engineers.add(engineer.id)
        engineers.append(engineer)

    meta = data.get("meta") or {}
    scenario = Scenario(
        region_key=region_key,
        region_name=region_name or str(meta.get("name") or region_key),
        orders=orders,
        engineers=engineers,
        cancelled_ids=[],
        geo_report={"exact": len(orders), "approx": 0, "coverage": 1.0,
                    "cache_path": "(координаты заданы в наборе)",
                    "cache_size": len(orders)},
    )
    events = data.get("events") or []
    if not isinstance(events, list):
        raise DatasetError("Поле «events» должно быть списком событий")
    return scenario, events


# --- определение формата присланного файла ------------------------------------

def load_upload(filename: str, raw: bytes, region_key: str,
                cache_path: str) -> tuple[Scenario, list[dict], str]:
    """Разбирает присланный файл, сам определяя формат.

    Возвращает (сценарий, события, описание распознанного формата).
    """
    if not raw.strip():
        raise DatasetError("Файл пустой")

    name = (filename or "").lower()
    head = raw[:4096].lstrip()

    # JSON узнаём по первому непробельному символу, а не только по расширению
    if head[:1] in (b"{", b"[") or name.endswith(".json"):
        try:
            data = json.loads(raw.decode("utf-8-sig"))
        except UnicodeDecodeError:
            raise DatasetError("JSON должен быть в кодировке UTF-8")
        except json.JSONDecodeError as exc:
            raise DatasetError(f"Не удалось разобрать JSON: {exc.msg} "
                               f"(строка {exc.lineno}, символ {exc.colno})")
        scenario, events = scenario_from_json(data, region_key)
        return scenario, events, "JSON, формат набора данных"

    if name.endswith(".csv") or b";" in head:
        text = decode_csv(raw)
        header = text.split("\n", 1)[0]
        if "Заявка" not in header:
            raise DatasetError(
                "В CSV не найдена колонка «Заявка». Ожидается выгрузка в "
                "формате организаторов: Заявка;Тип заявки BK;Статус BK;"
                "Тип заявки HD;Начало;Окончание;Район;Адрес;Бригада…")
        scenario = parse_control_csv(raw, region_key, cache_path)
        if not scenario.orders:
            raise DatasetError("В CSV не нашлось ни одной заявки")
        if not scenario.engineers:
            raise DatasetError(
                "В CSV нет колонки «Бригада» или она пустая: из такой выгрузки "
                "невозможно восстановить состав исполнителей. Загрузите набор "
                "в JSON, где исполнители заданы явно.")
        return scenario, [], "CSV, выгрузка в формате организаторов"

    raise DatasetError(
        "Неизвестный формат файла. Поддерживаются CSV в формате организаторов "
        "и JSON в формате набора данных — образец лежит в data/sample/.")
