"""Репозитории на настоящем PostgreSQL.

Двойник базы проверяет только наши представления о ней, поэтому тесты идут на
живом кластере. База берётся отдельная, тестовая, и пересоздаётся перед
прогоном: данные рабочей базы трогать нельзя.
"""
import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from dispatcher.infrastructure.db.base import Base
from dispatcher.infrastructure.db.repositories import (
    GeoRepository,
    PlanRepository,
    RegionRepository,
    SavedDayRepository,
)

TEST_DSN = os.environ.get(
    "DATABASE_TEST_URL",
    "postgresql+asyncpg://postgres@localhost:5432/dispatcher_test")

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def session():
    """Чистая схема на каждый тест, чтобы прогоны не зависели друг от друга."""
    engine = create_async_engine(TEST_DSN)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as active:
        yield active
    await engine.dispose()


async def test_region_is_saved_and_updated(session):
    regions = RegionRepository(session)
    await regions.save("vostok", "Восток", {"orders": 66}, "Офис", 55.7, 37.7)
    await regions.save("vostok", "Восток", {"orders": 70}, "Офис", 55.7, 37.7)

    stored = await regions.by_key("vostok")
    assert stored is not None
    assert stored.payload == {"orders": 70}
    assert len(await regions.list()) == 1


async def test_plan_versions_are_immutable_and_ordered(session):
    regions = RegionRepository(session)
    region = await regions.save("vostok", "Восток", {})
    plans = PlanRepository(session)

    first = await plans.add_version(region.id, {"assigned": 10}, "Расчёт")
    second = await plans.add_version(region.id, {"assigned": 12}, "Событие дня",
                                     parent_id=first.id)

    current = await plans.current(region.id)
    assert current is not None and current.id == second.id
    assert current.parent_id == first.id
    # Прежняя версия не тронута: правка создаёт следующую, а не меняет эту.
    assert first.payload == {"assigned": 10}
    assert [v.id for v in await plans.history(region.id)] == [second.id, first.id]


async def test_step_back_returns_previous_version(session):
    regions = RegionRepository(session)
    region = await regions.save("vostok", "Восток", {})
    plans = PlanRepository(session)
    first = await plans.add_version(region.id, {"assigned": 10}, "Расчёт")
    await plans.add_version(region.id, {"assigned": 12}, "Событие дня")

    back = await plans.drop_last(region.id)
    assert back is not None and back.id == first.id
    # Свёрнутая версия осталась в базе: историю дня не стирают.
    assert len(await plans.history(region.id)) == 1


async def test_geo_cache_round_trip(session):
    geo = GeoRepository(session)
    await geo.put("москва, ул ленина, д 1", 55.7, 37.6, "nominatim", "запрос")
    await geo.put("москва, ул ленина, д 1", 55.8, 37.7, "nominatim", "уточнён")

    stored = await geo.all()
    assert stored["москва, ул ленина, д 1"]["lat"] == 55.8
    assert len(stored) == 1


async def test_saved_day_round_trip(session):
    days = SavedDayRepository(session)
    await days.save("vostok", "утро", {"plan": 1})
    await days.save("vostok", "утро", {"plan": 2})

    stored = await days.get("vostok", "утро")
    assert stored is not None
    assert stored.payload == {"plan": 2}
    assert stored.saved_at is not None
    assert len(await days.list()) == 1
