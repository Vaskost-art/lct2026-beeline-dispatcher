"""Проверка отдельных полей присланного набора.

Негодное значение называется по имени и с указанием места: молча
потерянная запись выглядит как полный план, в котором заявки нет.
"""
from __future__ import annotations

import math
from typing import Any

from dispatcher.domain import parse_hhmm
from dispatcher.services.dataset.errors import DatasetError


def _require(data: dict, key: str, where: str) -> Any:
    if not isinstance(data, dict):
        raise DatasetError(f"{where}: ожидался объект с полями, получено "
                           f"«{data}»")
    if key not in data or data[key] in (None, ""):
        raise DatasetError(f"{where}: не заполнено обязательное поле «{key}»")
    return data[key]


# Сутки: время в наборе задаётся минутами от полуночи либо строкой ЧЧ:ММ.
DAY_MINUTES = 24 * 60


def _time(value: Any, where: str, key: str) -> int:
    """Принимает «ЧЧ:ММ» или число минут от полуночи."""
    if isinstance(value, bool):
        raise DatasetError(f"{where}: поле «{key}» должно быть временем")
    if isinstance(value, (int, float)):
        minutes = int(value)
        # Иначе набор с временем -100000 грузится успешно, а планирование
        # по нему падает на попытке задать диапазон решателю.
        if not 0 <= minutes <= DAY_MINUTES:
            raise DatasetError(
                f"{where}: поле «{key}» вне суток: {minutes} мин "
                f"(допустимо от 0 до {DAY_MINUTES})")
        return minutes
    try:
        return parse_hhmm(str(value))
    except (ValueError, AttributeError) as error:
        raise DatasetError(
            f"{where}: поле «{key}» должно быть временем в формате ЧЧ:ММ, "
            f"получено «{value}»") from error


def _coords(data: dict, where: str) -> tuple[float, float]:
    try:
        lat = float(_require(data, "lat", where))
        lon = float(_require(data, "lon", where))
    except (TypeError, ValueError) as error:
        raise DatasetError(f"{where}: координаты «lat» и «lon» должны быть числами") from error
    # NaN и Infinity json.loads принимает молча, а дальше они расходятся по
    # расстояниям и метрикам: план строится, но выгрузить его уже нельзя.
    if not (math.isfinite(lat) and math.isfinite(lon)):
        raise DatasetError(f"{where}: координаты «lat» и «lon» должны быть "
                           f"конечными числами")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise DatasetError(f"{where}: координаты вне карты: {lat}, {lon}")
    return lat, lon
