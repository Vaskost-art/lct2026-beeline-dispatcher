"""Чтение присланного набора данных.

Файл пришёл извне и считается враждебным: проверяется каждое поле, а
негодное значение называется по имени, а не роняет разбор молча.
"""
from __future__ import annotations

from dispatcher.domain import (
    PRIORITY_NORMAL,
    PRIORITY_URGENT,
    SKILL_LOCAL,
    VEHICLE_CAR,
    Engineer,
    Order,
    hhmm,
    norms,
)
from dispatcher.domain.scenario import Scenario
from dispatcher.services.dataset.errors import DatasetError
from dispatcher.services.dataset.fields import _coords, _require, _time


def order_from_json(data: dict) -> Order:
    order_id = str(_require(data, "id", "Заявка"))
    where = f"Заявка {order_id}"
    lat, lon = _coords(data, where)

    skill = str(data.get("required_skill") or SKILL_LOCAL)
    if skill not in norms.SKILL_BY_TYPE_BK.values():
        raise DatasetError(
            f"{where}: навык «{skill}» отсутствует в справочнике. "
            f"Допустимы: {', '.join(dict.fromkeys(norms.SKILL_BY_TYPE_BK.values()))}")

    vehicle = data.get("required_vehicle") or None
    if vehicle and vehicle not in norms.SPEED_KMH:
        raise DatasetError(
            f"{where}: транспорт «{vehicle}» отсутствует в справочнике. "
            f"Допустимы: {', '.join(norms.SPEED_KMH)}")

    priority = str(data.get("priority") or PRIORITY_NORMAL)
    if priority not in (PRIORITY_NORMAL, PRIORITY_URGENT):
        raise DatasetError(
            f"{where}: приоритет «{priority}» отсутствует в справочнике. "
            f"Допустимы: {PRIORITY_NORMAL}, {PRIORITY_URGENT}")

    try:
        duration = int(str(_require(data, "duration_min", where)))
    except (TypeError, ValueError) as error:
        raise DatasetError(f"{where}: «duration_min» должно быть числом минут") from error
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
        equipment=[str(item) for item in (data.get("equipment") or [])],
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

    vehicle = str(data.get("vehicle") or VEHICLE_CAR)
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
    except (TypeError, ValueError) as error:
        raise DatasetError(f"{where}: «break_min» должно быть числом минут") from error
    # Пустая смена без перерыва законна: так описывается исполнитель, который
    # в этот день не работает.
    empty_shift = allow_empty_shift and shift_end == shift_start and break_min == 0
    if not empty_shift and not 0 <= break_min < max(1, shift_end - shift_start):
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
