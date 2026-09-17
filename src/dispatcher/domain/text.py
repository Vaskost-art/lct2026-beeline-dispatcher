"""Мелочи русского текста, общие для всех слоёв."""
from __future__ import annotations


def plural(n: int, one: str, few: str, many: str) -> str:
    """Форма слова при числе: 1 заявка, 2 заявки, 5 заявок."""
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many
