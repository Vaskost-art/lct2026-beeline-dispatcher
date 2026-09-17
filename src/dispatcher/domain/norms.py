"""Нормативы и правила восстановления полей, которых нет в исходных данных.

Исходные выгрузки — реальные обезличенные наряды FSM. В них есть тип работ,
адрес, район и временное окно, но НЕТ длительности, навыков, транспорта и смен.
Всё, что мы достраиваем, собрано здесь в одном месте: каждое допущение можно
показать эксперту и поменять одной строкой.

Источник правил — справочники ТЗ (п. 2.4.1) и структура самих данных.
"""
from __future__ import annotations

from dispatcher.domain.catalog import (
    PRIORITY_NORMAL,
    PRIORITY_URGENT,
    SKILL_CONNECT,
    SKILL_EMERGENCY,
    SKILL_LOCAL,
    VEHICLE_BIKE,
    VEHICLE_CAR,
    VEHICLE_FOOT,
    VEHICLE_TRANSIT,
)

# --- 1. Навык -----------------------------------------------------------------
# Колонка «Тип заявки BK» ложится на справочник навыков ТЗ один в один.
SKILL_BY_TYPE_BK = {
    "Локальная заявка": SKILL_LOCAL,
    "Подключение": SKILL_CONNECT,
    "Дозаказ": SKILL_CONNECT,
    "Глобальная проблема": SKILL_EMERGENCY,
}
DEFAULT_SKILL = SKILL_LOCAL

# --- 2. Длительность работ, минуты -------------------------------------------
# Нормативы по «Тип заявки HD». Значения — отраслевые ориентиры для монтажных
# работ ШПД: подключение с прокладкой кабеля дольше, диагностика и замена
# абонентского оборудования короче.
DURATION_BY_TYPE_HD = {
    # подключения и дозаказы
    "Конвергенция абонента": 90,
    "Заявка на подключение": 120,
    "Заказ подключения/Дозаказ оборудования": 90,
    "Дозаказ оборудования": 60,
    # аварии
    "Авария": 120,
    "Информация": 30,
    # локальные работы
    "Нет линка": 60,
    "Работа с кабелем": 90,
    "Переключение на Гбит/с": 60,
    "Разрывы": 45,
    "Низкая скорость": 45,
    "Рост ошибок на порту": 45,
    "IP-адрес 169...": 30,
    "Мониторинг": 30,
    "Роутер. Замена техническим специалистом": 40,
    "TVE/ENT. Замена приставки техником": 40,
    "ТВ. Замена приставки техником": 40,
    "TVE/ENT. Другие ошибки": 40,
}
DEFAULT_DURATION = 60

# Гигабитное подключение требует протяжки нового кабеля — надбавка к норме.
GIGABIT_EXTRA_MIN = 30

# --- 3. Приоритет -------------------------------------------------------------
# «Срочная» = авария (влияет на многих абонентов) либо уже просроченный наряд.
URGENT_TYPES_BK = {"Глобальная проблема"}
URGENT_STATUSES_BK = {"Просрочена"}

# --- 4. Требуемый тип транспорта (ограничение «Ресурс» из ТЗ) ------------------
# Ограничение ставится только там, где работа физически требует машины:
# тяжёлое оборудование, бухта кабеля, инструмент аварийной бригады.
# В остальных заявках ограничения нет (ТЗ: «указывается только при наличии»).
CAR_REQUIRED_TYPES_HD = {"Авария", "Работа с кабелем"}
CAR_REQUIRED_IF_GIGABIT = True

# --- 5. Скорости движения, км/ч ----------------------------------------------
# Средние скорости «от двери до двери» в Москве с учётом трафика и парковки.
SPEED_KMH = {
    VEHICLE_CAR: 22.0,
    VEHICLE_TRANSIT: 15.0,
    VEHICLE_BIKE: 12.0,
    VEHICLE_FOOT: 4.5,
}

# Коэффициент извилистости: по прямой (haversine) -> по улично-дорожной сети.
# 1.35 — общепринятая оценка для плотной городской застройки.
DETOUR_FACTOR = 1.35


def skill_for(type_bk: str) -> str:
    return SKILL_BY_TYPE_BK.get(type_bk.strip(), DEFAULT_SKILL)


def duration_for(type_hd: str, gigabit: bool) -> int:
    base = DURATION_BY_TYPE_HD.get(type_hd.strip(), DEFAULT_DURATION)
    return base + (GIGABIT_EXTRA_MIN if gigabit else 0)


def priority_for(type_bk: str, status_bk: str) -> str:
    if type_bk.strip() in URGENT_TYPES_BK:
        return PRIORITY_URGENT
    if status_bk.strip() in URGENT_STATUSES_BK:
        return PRIORITY_URGENT
    return PRIORITY_NORMAL


def required_vehicle_for(type_hd: str, gigabit: bool) -> str | None:
    if type_hd.strip() in CAR_REQUIRED_TYPES_HD:
        return VEHICLE_CAR
    if gigabit and CAR_REQUIRED_IF_GIGABIT:
        return VEHICLE_CAR
    return None
