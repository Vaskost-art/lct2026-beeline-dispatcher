"""Запись сценария в JSON."""
from __future__ import annotations

from dispatcher.domain import PRIORITY_NORMAL, PRIORITY_URGENT, Engineer, Order, hhmm, norms
from dispatcher.domain.catalog import VEHICLES
from dispatcher.domain.scenario import Scenario
from dispatcher.services.dataset.errors import FORMAT_VERSION


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
        "equipment": list(order.equipment),
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
                "vehicles": list(VEHICLES),
                "priorities": [PRIORITY_NORMAL, PRIORITY_URGENT],
            },
        },
        "orders": [order_to_json(o) for o in scenario.orders],
        "engineers": [engineer_to_json(e) for e in scenario.engineers],
        "events": events or [],
    }
