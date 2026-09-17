"""Из кого состоит бригада участка: квалификация и транспорт.

В синтетических данных исполнителей нет вообще, поэтому состав определяем мы
сами. Постановщик задал рамку: три квалификации по типам работ, справочника
не будет, генерировать самим и показать влияние на маршрут; транспорт
задавать в любой доле, в жизни преобладают пешие и на общественном.

Все числа здесь объявлены допущениями и показываются диспетчеру.
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

#: Наборы квалификаций и доля бригад с таким набором.
#: Универсалов меньшинство: в жизни широкая квалификация редка и дорога.
SKILL_PROFILES: tuple[tuple[tuple[str, ...], float], ...] = (
    ((SKILL_CONNECT, SKILL_LOCAL), 0.45),
    ((SKILL_LOCAL, SKILL_EMERGENCY), 0.25),
    ((SKILL_CONNECT, SKILL_LOCAL, SKILL_EMERGENCY), 0.20),
    ((SKILL_CONNECT,), 0.10),
)

#: Доли транспорта. Авария и работа с кабелем требуют машины, поэтому
#: автомобильных бригад всегда хватает на такие заявки: доля - нижняя граница.
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
