"""Справочники из ТЗ: навыки, транспорт, приоритеты."""
from __future__ import annotations

# --- Справочники из ТЗ (п. 2.4.1) -------------------------------------------

SKILL_LOCAL = "Локальные работы"
SKILL_CONNECT = "Работы на подключение и дозаказы"
SKILL_EMERGENCY = "Аварийные работы"
SKILLS = (SKILL_LOCAL, SKILL_CONNECT, SKILL_EMERGENCY)

VEHICLE_CAR = "Автомобиль"
VEHICLE_FOOT = "Пешеход"
VEHICLE_BIKE = "Велосипед"
VEHICLE_TRANSIT = "Общественный транспорт"
VEHICLES = (VEHICLE_CAR, VEHICLE_FOOT, VEHICLE_BIKE, VEHICLE_TRANSIT)

PRIORITY_NORMAL = "Обычная"
PRIORITY_URGENT = "Срочная"
#: Подключение: второй приоритет после аварии. Постановщик задал порядок
#: «Авария - Подключение - Ремонт / Дозаказ» и просил рассматривать остальное
#: по остаточному принципу (чат 19.09, ответ 15).
PRIORITY_HIGH = "Повышенная"
PRIORITIES = (PRIORITY_NORMAL, PRIORITY_HIGH, PRIORITY_URGENT)


