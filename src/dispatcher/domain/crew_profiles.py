"""Из кого состоит бригада участка: квалификация и транспорт.

В синтетических данных исполнителей нет вообще, поэтому состав определяем мы
сами. Постановщик задал рамку: три квалификации по типам работ, справочника
не будет, генерировать самим и показать влияние на маршрут; транспорт
задавать в любой доле, в жизни преобладают пешие и на общественном.

Доли профилей и транспорта - допущения модели, их видно в документации.
"""
from __future__ import annotations

from dispatcher.domain.catalog import (
    SKILL_CONNECT,
    SKILL_EMERGENCY,
    SKILL_LOCAL,
    VEHICLE_CAR,
    VEHICLE_FOOT,
    VEHICLE_TRANSIT,
)
from dispatcher.domain.models import Order

#: Наборы квалификаций и доля бригад с таким набором.
#: Универсалов меньшинство: в жизни широкая квалификация редка и дорога.
SKILL_PROFILES: tuple[tuple[tuple[str, ...], float], ...] = (
    ((SKILL_CONNECT, SKILL_LOCAL), 0.45),
    ((SKILL_LOCAL, SKILL_EMERGENCY), 0.25),
    ((SKILL_CONNECT, SKILL_LOCAL, SKILL_EMERGENCY), 0.20),
    ((SKILL_CONNECT,), 0.10),
)

#: Доли транспорта для бригад сверх обязательных машин. Сколько машин
#: обязательно, считается по заявкам, где машина нужна (`cars_needed`), и
#: достаются они бригадам с подходящим допуском (`assign_vehicles`).
VEHICLE_SHARES: tuple[tuple[str, float], ...] = (
    (VEHICLE_TRANSIT, 0.45),
    (VEHICLE_FOOT, 0.30),
    (VEHICLE_CAR, 0.25),
)


def skills_for_index(index: int, total: int) -> list[str]:
    """Квалификация бригады номер `index` из `total` по долям профилей."""
    if total <= 0:
        return list(SKILL_PROFILES[0][0])
    boundary = 0.0
    position = (index + 0.5) / total
    for skills, share in SKILL_PROFILES:
        boundary += share
        if position <= boundary:
            return list(skills)
    return list(SKILL_PROFILES[-1][0])


def vehicle_for_index(index: int, total: int, need_car: int) -> str:
    """Транспорт бригады номер `index` из `total`.

    Первые `need_car` бригад получают автомобиль: без него заявки, где машина
    обязательна, не выполнит никто, и план потеряет их не по своей вине.
    """
    if index < need_car:
        return VEHICLE_CAR
    if total <= 0:
        return VEHICLE_TRANSIT
    boundary = 0.0
    position = (index - need_car + 0.5) / max(1, total - need_car)
    for vehicle, share in VEHICLE_SHARES:
        boundary += share
        if position <= boundary:
            return vehicle
    return VEHICLE_SHARES[-1][0]


def assign_vehicles(skills: list[list[str]], orders: list[Order],
                    need_car: int) -> list[str]:
    """Транспорт для бригад с известной квалификацией.

    Обязательные машины достаются тем, кто умеет больше всего заявок, где
    машина нужна: авария без машины невыполнима, и машина у бригады без
    допуска к авариям её не спасёт. Раньше машины раздавались по номеру
    бригады, а допуск к авариям - по долям, и на Востоке ни одна машина не
    умела аварии: все три утренние аварии оставались без исполнителя.
    Остальные бригады получают транспорт по долям, как прежде.
    """
    total = len(skills)
    car_orders = [o for o in orders if o.required_vehicle == VEHICLE_CAR]
    fit = [sum(1 for o in car_orders if o.required_skill in crew) for crew in skills]
    cars = set(sorted(range(total), key=lambda i: (-fit[i], i))[:need_car])
    vehicles: list[str] = []
    rest = 0
    for index in range(total):
        if index in cars:
            vehicles.append(VEHICLE_CAR)
            continue
        vehicles.append(vehicle_for_index(need_car + rest, total, need_car))
        rest += 1
    # Авария может прийти днём, а днём она едет на машине. Если утренние
    # машины достались другим, одна бригада с допуском к авариям получает
    # машину сверх них: иначе участок не примет ни одной дневной аварии.
    rescuers = [i for i in range(total) if SKILL_EMERGENCY in skills[i]]
    if rescuers and not any(vehicles[i] == VEHICLE_CAR for i in rescuers):
        vehicles[rescuers[0]] = VEHICLE_CAR
    return vehicles
