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



# --- Состояние заявки в течение дня (чат 19.09, ответы 1 и 8) ---------------
# Организаторы: «Статус заявки изменяется по мере её выполнения. Основные
# состояния: „Отправлено“ - заявка поступила исполнителю; „В пути“ - бригада
# направляется к месту выполнения; далее заявка переходит к выполнению;
# „Завершено“ - работы закончены. Статус „Отменена“ может появиться при
# отказе клиента либо когда бригада определила, что выполнить заявку
# невозможно». Факт закрытия фиксирует диспетчер со слов бригады.
STATUS_SENT = "Отправлено"
STATUS_ON_WAY = "В пути"
STATUS_WORKING = "Выполняется"
STATUS_DONE = "Завершено"
STATUS_CANCELLED = "Отменена"

#: Порядок как в жизни смены: от выдачи наряда до закрытия.
STATUSES = (STATUS_SENT, STATUS_ON_WAY, STATUS_WORKING, STATUS_DONE,
            STATUS_CANCELLED)

#: Заявки, которые больше не планируются: работа закончена или отменена.
CLOSED_STATUSES = frozenset({STATUS_DONE, STATUS_CANCELLED})

#: Заявки, которые бригада уже начала и снимать их нельзя.
STARTED_STATUSES = frozenset({STATUS_ON_WAY, STATUS_WORKING})
