"""Подключение к базе и выдача сессий.

Адрес базы берётся из окружения: в `.env` рядом с проектом либо из переменных
процесса. Пароль в коде не лежит и в репозиторий не попадает.

Слой синхронный: ручки сервиса тоже синхронные, диспетчер один, а запрос к
базе идёт раз в несколько секунд. Асинхронный драйвер здесь давал только
несовместимость с остальным кодом.
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from dispatcher.infrastructure import envfile

#: Адрес базы по умолчанию: локальный кластер разработчика без пароля.
DEFAULT_DSN = "postgresql+psycopg://postgres@localhost:5432/dispatcher"

_engine: Engine | None = None
_sessions: sessionmaker[Session] | None = None


def dsn() -> str:
    """Адрес базы из окружения."""
    envfile.load()
    return os.environ.get("DATABASE_URL", "").strip() or DEFAULT_DSN


def engine() -> Engine:
    """Общий движок подключения."""
    global _engine, _sessions
    if _engine is None:
        _engine = create_engine(dsn(), pool_pre_ping=True)
        _sessions = sessionmaker(_engine, expire_on_commit=False)
    return _engine


@contextmanager
def session() -> Iterator[Session]:
    """Сессия на одну единицу работы."""
    engine()
    assert _sessions is not None
    with _sessions() as active:
        yield active


def dispose() -> None:
    """Закрывает подключения: нужно при остановке сервиса и в тестах."""
    global _engine, _sessions
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _sessions = None
