"""Основание для моделей базы: общие поля и правила.

На бизнес-таблицах есть `deleted_at`: физическое удаление запрещено, запись
помечается удалённой и перестаёт попадать в выборки. Колонка владельца
заложена сразу, хотя вход в систему не делается: пользователь один, диспетчер,
и авторизация заказчиком не требуется.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

#: Кто владеет записями, пока учётных записей нет. Колонка существует, чтобы
#: разделение по владельцу не пришлось добавлять миграцией по всем таблицам.
DEFAULT_OWNER = "default"


class Base(DeclarativeBase):
    """Общее основание всех таблиц."""


class Owned:
    """Поля, которые есть у каждой бизнес-таблицы."""

    owner_id: Mapped[str] = mapped_column(String(64), default=DEFAULT_OWNER,
                                          index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                        default=None, index=True)
