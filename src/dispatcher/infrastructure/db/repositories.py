"""Репозитории: единственное место, где живёт обращение к базе.

Сервисы получают репозиторий снаружи и про SQLAlchemy ничего не знают. Ни
одна выборка не возвращает удалённые записи: физического удаления в проекте
нет, вместо него проставляется `deleted_at`.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dispatcher.infrastructure.db.base import DEFAULT_OWNER
from dispatcher.infrastructure.db.models import (
    GeoPoint,
    JsonDict,
    PlanVersion,
    Region,
    SavedDay,
)


class RegionRepository:
    """Участки и их наборы данных."""

    def __init__(self, session: AsyncSession, owner_id: str = DEFAULT_OWNER) -> None:
        self._session = session
        self._owner_id = owner_id

    async def list(self) -> list[Region]:
        rows = await self._session.scalars(
            select(Region)
            .where(Region.owner_id == self._owner_id, Region.deleted_at.is_(None))
            .order_by(Region.id))
        return list(rows)

    async def by_key(self, key: str) -> Region | None:
        found: Region | None = await self._session.scalar(
            select(Region).where(Region.owner_id == self._owner_id,
                                 Region.key == key,
                                 Region.deleted_at.is_(None)))
        return found

    async def save(self, key: str, name: str, payload: JsonDict,
                   office_address: str = "", office_lat: float = 0.0,
                   office_lon: float = 0.0) -> Region:
        """Записывает участок, обновляя существующий."""
        region = await self.by_key(key)
        if region is None:
            region = Region(owner_id=self._owner_id, key=key)
            self._session.add(region)
        region.name = name
        region.payload = payload
        region.office_address = office_address
        region.office_lat = office_lat
        region.office_lon = office_lon
        await self._session.flush()
        return region


class PlanRepository:
    """Версии плана. Версия неизменяема: правка создаёт следующую."""

    def __init__(self, session: AsyncSession, owner_id: str = DEFAULT_OWNER) -> None:
        self._session = session
        self._owner_id = owner_id

    async def add_version(self, region_id: int, payload: JsonDict, label: str,
                          strategy: str = "", solver_status: str = "",
                          solve_seconds: float = 0.0,
                          locked: JsonDict | None = None,
                          parent_id: int | None = None) -> PlanVersion:
        version = PlanVersion(
            owner_id=self._owner_id,
            region_id=region_id,
            parent_id=parent_id,
            label=label,
            strategy=strategy,
            solver_status=solver_status,
            solve_seconds=solve_seconds,
            payload=payload,
            locked=locked or {},
        )
        self._session.add(version)
        await self._session.flush()
        return version

    async def current(self, region_id: int) -> PlanVersion | None:
        """Последняя версия плана участка."""
        found: PlanVersion | None = await self._session.scalar(
            select(PlanVersion)
            .where(PlanVersion.owner_id == self._owner_id,
                   PlanVersion.region_id == region_id,
                   PlanVersion.deleted_at.is_(None))
            .order_by(PlanVersion.id.desc())
            .limit(1))
        return found

    async def history(self, region_id: int, limit: int = 20) -> list[PlanVersion]:
        """Последние версии, новые первыми: из них собирается «шаг назад»."""
        rows = await self._session.scalars(
            select(PlanVersion)
            .where(PlanVersion.owner_id == self._owner_id,
                   PlanVersion.region_id == region_id,
                   PlanVersion.deleted_at.is_(None))
            .order_by(PlanVersion.id.desc())
            .limit(limit))
        return list(rows)

    async def drop_last(self, region_id: int) -> PlanVersion | None:
        """Шаг назад: последняя версия помечается удалённой.

        Запись остаётся в базе: историю дня не стирают, её сворачивают.
        """
        last = await self.current(region_id)
        if last is None:
            return None
        last.deleted_at = datetime.now(UTC)
        await self._session.flush()
        return await self.current(region_id)


class GeoRepository:
    """Кэш координат адресов."""

    def __init__(self, session: AsyncSession, owner_id: str = DEFAULT_OWNER) -> None:
        self._session = session
        self._owner_id = owner_id

    async def all(self) -> dict[str, dict[str, object]]:
        rows = await self._session.scalars(
            select(GeoPoint).where(GeoPoint.deleted_at.is_(None)))
        return {
            row.address_key: {"lat": row.lat, "lon": row.lon,
                              "source": row.source, "query": row.query}
            for row in rows
        }

    async def put(self, address_key: str, lat: float | None, lon: float | None,
                  source: str = "", query: str = "") -> None:
        point = await self._session.scalar(
            select(GeoPoint).where(GeoPoint.address_key == address_key))
        if point is None:
            point = GeoPoint(owner_id=self._owner_id, address_key=address_key)
            self._session.add(point)
        point.lat, point.lon = lat, lon
        point.source, point.query = source, query
        await self._session.flush()


class SavedDayRepository:
    """Сохранённые рабочие дни."""

    def __init__(self, session: AsyncSession, owner_id: str = DEFAULT_OWNER) -> None:
        self._session = session
        self._owner_id = owner_id

    async def save(self, region_key: str, name: str, payload: JsonDict) -> SavedDay:
        day = await self.get(region_key, name)
        if day is None:
            day = SavedDay(owner_id=self._owner_id, region_key=region_key, name=name)
            self._session.add(day)
        day.payload = payload
        day.saved_at = datetime.now(UTC)
        await self._session.flush()
        return day

    async def get(self, region_key: str, name: str = "") -> SavedDay | None:
        found: SavedDay | None = await self._session.scalar(
            select(SavedDay).where(SavedDay.owner_id == self._owner_id,
                                   SavedDay.region_key == region_key,
                                   SavedDay.name == name,
                                   SavedDay.deleted_at.is_(None)))
        return found

    async def list(self) -> list[SavedDay]:
        rows = await self._session.scalars(
            select(SavedDay)
            .where(SavedDay.owner_id == self._owner_id,
                   SavedDay.deleted_at.is_(None))
            .order_by(SavedDay.saved_at.desc()))
        return list(rows)
