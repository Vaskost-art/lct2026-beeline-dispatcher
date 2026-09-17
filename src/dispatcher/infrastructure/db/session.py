"""Подключение к базе и выдача сессий.

Адрес базы берётся из окружения: в `.env` рядом с проектом либо из переменных
процесса. Пароль в коде не лежит и в репозиторий не попадает.
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from dispatcher.infrastructure import envfile

#: Адрес базы по умолчанию: локальный кластер разработчика без пароля.
DEFAULT_DSN = "postgresql+asyncpg://postgres@localhost:5432/dispatcher"

_engine: AsyncEngine | None = None
_sessions: async_sessionmaker[AsyncSession] | None = None


def dsn() -> str:
    """Адрес базы из окружения."""
    envfile.load()
    return os.environ.get("DATABASE_URL", "").strip() or DEFAULT_DSN


def engine() -> AsyncEngine:
    """Общий движок подключения."""
    global _engine, _sessions
    if _engine is None:
        _engine = create_async_engine(dsn(), pool_pre_ping=True)
        _sessions = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


@asynccontextmanager
async def session() -> AsyncIterator[AsyncSession]:
    """Сессия на одну единицу работы."""
    engine()
    assert _sessions is not None
    async with _sessions() as active:
        yield active


async def dispose() -> None:
    """Закрывает подключения: нужно при остановке сервиса и в тестах."""
    global _engine, _sessions
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessions = None
