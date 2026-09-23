"""Правила рабочего дня исполнителя: транспорт, перерыв, границы смены."""
from __future__ import annotations

from dispatcher.domain.catalog import VEHICLE_BIKE, VEHICLE_CAR, VEHICLE_FOOT, VEHICLE_TRANSIT

# --- 6. Правила восстановления транспорта исполнителя -------------------------
# Тип транспорта выводится из географии реальных маршрутов бригады в
# контрольном распределении: чем шире разлёт точек, тем «быстрее» транспорт.
SPREAD_CAR_KM = 6.0        # разлёт больше - только автомобиль
SPREAD_TRANSIT_KM = 3.0    # средний разлёт в центре - общественный транспорт
SPREAD_BIKE_KM = 1.5       # компактный участок - велосипед
                           # меньше - пешком

# Районы исторического центра: там быстрее на метро, чем на машине.
CENTRAL_DISTRICTS = {
    "Хамовники", "Замоскворечье", "Басманный", "Таганский", "Даниловский",
    "Донской", "Гагаринский",
}

# --- 6.1. Перерыв на обед -----------------------------------------------------
# Смена считалась сплошной, и это завышало ёмкость дня почти на час на бригаду.
# Время обеда не фиксируется: эти минуты вычитаются из ёмкости дня. Жёсткий
# интервал в модели пробовался и был отвергнут - он ухудшал пробег на 13–38%,
# не давая взамен ничего, кроме точного времени обеда.
BREAK_MIN = 45                  # длительность перерыва
BREAK_MIN_SHIFT_MIN = 6 * 60    # смена короче - работают без перерыва

# --- 7. Смена -----------------------------------------------------------------
SHIFT_LEAD_MIN = 60        # запас до первого окна на дорогу от базы
SHIFT_TAIL_MIN = 30        # запас после последнего окна
SHIFT_MIN_LENGTH_MIN = 8 * 60
SHIFT_EARLIEST = 8 * 60    # 08:00
SHIFT_LATEST = 23 * 60     # 23:00


def vehicle_for_spread(spread_km: float, needs_car: bool, central: bool) -> str:
    """Тип транспорта бригады по разлёту её точек в контрольном распределении."""
    if needs_car or spread_km >= SPREAD_CAR_KM:
        return VEHICLE_CAR
    if central and spread_km >= SPREAD_BIKE_KM:
        return VEHICLE_TRANSIT
    if spread_km >= SPREAD_TRANSIT_KM:
        return VEHICLE_CAR
    if spread_km >= SPREAD_BIKE_KM:
        return VEHICLE_BIKE
    return VEHICLE_FOOT


def break_minutes(shift_start: int, shift_end: int) -> int:
    """Сколько минут смены уходит на перерыв. Короткая смена - без перерыва."""
    if shift_end - shift_start < BREAK_MIN_SHIFT_MIN:
        return 0
    return BREAK_MIN


def shift_bounds(first_window_start: int, last_window_end: int) -> tuple[int, int]:
    """Границы смены по диапазону окон реально выполненных заявок."""
    start = max(SHIFT_EARLIEST, first_window_start - SHIFT_LEAD_MIN)
    end = min(SHIFT_LATEST, last_window_end + SHIFT_TAIL_MIN)
    if end - start < SHIFT_MIN_LENGTH_MIN:
        end = min(SHIFT_LATEST, start + SHIFT_MIN_LENGTH_MIN)
        if end - start < SHIFT_MIN_LENGTH_MIN:
            start = max(SHIFT_EARLIEST, end - SHIFT_MIN_LENGTH_MIN)
    return start, end
