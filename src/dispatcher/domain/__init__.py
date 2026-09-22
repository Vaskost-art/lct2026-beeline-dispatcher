"""Доменные сущности и правила.

Слой ничего не знает ни о HTTP, ни о базе, ни о файлах. Публичные имена
собраны здесь, чтобы остальные слои импортировали домен одной строкой.
"""
from dispatcher.domain.catalog import (
                                       PRIORITIES,
                                       PRIORITY_HIGH,
                                       PRIORITY_NORMAL,
                                       PRIORITY_URGENT,
                                       SKILL_CONNECT,
                                       SKILL_EMERGENCY,
                                       SKILL_LOCAL,
                                       SKILLS,
                                       VEHICLE_BIKE,
                                       VEHICLE_CAR,
                                       VEHICLE_FOOT,
                                       VEHICLE_TRANSIT,
                                       VEHICLES,
)
from dispatcher.domain.clock import hhmm, parse_hhmm
from dispatcher.domain.models import Engineer, Order
from dispatcher.domain.plan import Plan, Route, Stop, Unassigned

__all__ = [
    "PRIORITIES", "PRIORITY_HIGH", "PRIORITY_NORMAL", "PRIORITY_URGENT",
    "SKILLS", "SKILL_CONNECT", "SKILL_EMERGENCY", "SKILL_LOCAL",
    "VEHICLES", "VEHICLE_BIKE", "VEHICLE_CAR", "VEHICLE_FOOT",
    "VEHICLE_TRANSIT",
    "Engineer", "Order", "Plan", "Route", "Stop", "Unassigned",
    "hhmm", "parse_hhmm",
]
