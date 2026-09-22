"""Общие фикстуры тестов."""
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(ROOT, "data", "raw")
CACHE = os.path.join(ROOT, "data", "geo_cache.json")

TEST_DSN = os.environ.get(
    "DATABASE_TEST_URL",
    "postgresql+psycopg://postgres@localhost:5432/dispatcher_test")


@pytest.fixture(scope="session", autouse=True)
def test_database():
    """Весь прогон работает с тестовой базой, а не с рабочей.

    Сервис пишет версии дня в базу, и без этой подмены прогон тестов
    складывал бы их в рабочую: адрес базы берётся из окружения, а окружение
    у тестов и у сервиса одно.
    """
    os.environ["DATABASE_URL"] = TEST_DSN
    from sqlalchemy import create_engine

    from dispatcher.infrastructure.db.base import Base

    engine = create_engine(TEST_DSN)
    with engine.begin() as connection:
        Base.metadata.drop_all(connection)
        Base.metadata.create_all(connection)
    engine.dispose()
    yield TEST_DSN


@pytest.fixture(scope="session")
def scenarios():
    """Все участки, загруженные из выгрузок заказчика."""
    from dispatcher.services.scenario import load_all

    return load_all(RAW_DIR, CACHE)
