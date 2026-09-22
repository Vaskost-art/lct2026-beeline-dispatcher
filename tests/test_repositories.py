"""Репозитории на настоящем PostgreSQL.

Двойник базы проверяет только наши представления о ней, поэтому тесты идут на
живом кластере. База берётся отдельная, тестовая, и пересоздаётся перед
прогоном: данные рабочей базы трогать нельзя.
"""
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from dispatcher.infrastructure.db.base import Base
from dispatcher.infrastructure.db.repositories import (
    GeoRepository,
    PlanRepository,
    RegionRepository,
    SavedDayRepository,
)

TEST_DSN = os.environ.get(
    "DATABASE_TEST_URL",
    "postgresql+psycopg://postgres@localhost:5432/dispatcher_test")


@pytest.fixture
def session():
    """Чистая схема на каждый тест, чтобы прогоны не зависели друг от друга."""
    engine = create_engine(TEST_DSN)
    with engine.begin() as connection:
        Base.metadata.drop_all(connection)
        Base.metadata.create_all(connection)
    maker = sessionmaker(engine, expire_on_commit=False)
    with maker() as active:
        yield active
    engine.dispose()


def test_region_is_saved_and_updated(session):
    regions = RegionRepository(session)
    regions.save("vostok", "Восток", {"orders": 66}, "Офис", 55.7, 37.7)
    regions.save("vostok", "Восток", {"orders": 70}, "Офис", 55.7, 37.7)

    stored = regions.by_key("vostok")
    assert stored is not None
    assert stored.payload == {"orders": 70}
    assert len(regions.list()) == 1


def test_plan_versions_are_immutable_and_ordered(session):
    regions = RegionRepository(session)
    region = regions.save("vostok", "Восток", {})
    plans = PlanRepository(session)

    first = plans.add_version(region.id, {"assigned": 10}, "Расчёт")
    second = plans.add_version(region.id, {"assigned": 12}, "Событие дня",
                                parent_id=first.id)

    current = plans.current(region.id)
    assert current is not None and current.id == second.id
    assert current.parent_id == first.id
    # Прежняя версия не тронута: правка создаёт следующую, а не меняет эту.
    assert first.payload == {"assigned": 10}
    assert [v.id for v in plans.history(region.id)] == [second.id, first.id]


def test_step_back_returns_previous_version(session):
    regions = RegionRepository(session)
    region = regions.save("vostok", "Восток", {})
    plans = PlanRepository(session)
    first = plans.add_version(region.id, {"assigned": 10}, "Расчёт")
    plans.add_version(region.id, {"assigned": 12}, "Событие дня")

    back = plans.drop_last(region.id)
    assert back is not None and back.id == first.id
    # Свёрнутая версия осталась в базе: историю дня не стирают.
    assert len(plans.history(region.id)) == 1


def test_geo_cache_round_trip(session):
    geo = GeoRepository(session)
    geo.put("москва, ул ленина, д 1", 55.7, 37.6, "nominatim", "запрос")
    geo.put("москва, ул ленина, д 1", 55.8, 37.7, "nominatim", "уточнён")

    stored = geo.all()
    assert stored["москва, ул ленина, д 1"]["lat"] == 55.8
    assert len(stored) == 1


def test_saved_day_round_trip(session):
    days = SavedDayRepository(session)
    days.save("vostok", "утро", {"plan": 1})
    days.save("vostok", "утро", {"plan": 2})

    stored = days.get("vostok", "утро")
    assert stored is not None
    assert stored.payload == {"plan": 2}
    assert stored.saved_at is not None
    assert len(days.list()) == 1
