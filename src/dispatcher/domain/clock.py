"""Время суток: минуты от полуночи и запись ЧЧ:ММ."""
from __future__ import annotations


def hhmm(minutes: int) -> str:
    """Минуты от полуночи -> 'HH:MM'. Поддерживает выход за 24:00."""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def parse_hhmm(text: str) -> int:
    """'ЧЧ:ММ' -> минуты от полуночи.

    Проверяет диапазон: без этого «25:99» разбиралось бы молча и уезжало
    за пределы суток, ломая окна и смены дальше по цепочке.
    """
    parts = str(text).strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"время должно быть в формате ЧЧ:ММ, получено «{text}»")
    hours, minutes = parts
    if not (hours.isdigit() and minutes.isdigit()):
        raise ValueError(f"время должно быть в формате ЧЧ:ММ, получено «{text}»")
    h, m = int(hours), int(minutes)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f"время «{text}» вне суток: часы 00–23, минуты 00–59")
    return h * 60 + m
