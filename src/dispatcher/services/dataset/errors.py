"""Ошибка разбора присланного набора и версия формата."""
from __future__ import annotations

FORMAT_VERSION = 1


class DatasetError(ValueError):
    """Присланный набор данных не удалось разобрать."""
