"""Чтение выгрузок заказчика: кодировка, разделитель, разбор ячеек.

Файл приходит извне и считается враждебным: кодировка может быть любой
из двух, ячейка может отсутствовать, дата может быть пустой.
"""
from __future__ import annotations

from collections.abc import Mapping

from dispatcher.domain import parse_hhmm

RAW_ENCODING = "cp1251"
CSV_DELIMITER = ";"


def decode_csv(raw: bytes) -> str:
    """Определяет кодировку выгрузки: организаторы отдают cp1251, но файл
    могли пересохранить в UTF-8, в том числе с BOM."""
    for encoding in ("utf-8-sig", RAW_ENCODING, "utf-8"):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        # cp1251 декодирует почти что угодно, поэтому проверяем осмысленность:
        # в шапке обязана быть колонка «Заявка»
        if "Заявка" in text.split("\n", 1)[0]:
            return text
    return raw.decode(RAW_ENCODING, errors="replace")


def _cell(row: Mapping[str, str | None], name: str) -> str:
    """Значение колонки строкой. В короткой строке CSV недостающие ключи
    приходят как None, поэтому .get(name, "") от падения не спасает."""
    return (row.get(name) or "").strip()


def _parse_dt(value: str) -> int | None:
    """'17.08.2026 20:00' -> минуты от полуночи. None, если поле пустое."""
    value = value.strip()
    if not value:
        return None
    parts = value.split()
    if len(parts) != 2:
        return None
    try:
        return parse_hhmm(parts[1])
    except ValueError:
        return None


def _clean_address(raw: str) -> str:
    """Убирает дубль «г.Город Москва» и номер квартиры для отображения."""
    addr = raw.strip()
    addr = addr.replace("г.Город Москва", "Москва").replace("Город Москва", "Москва")
    return addr.strip(" ,")
