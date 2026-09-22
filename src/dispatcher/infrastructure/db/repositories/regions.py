"""Участки и версии плана: два справочника одного дня.

Версия плана неизменяема. Правка не меняет запись, а создаёт следующую -
отсюда история дня и шаг назад."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from dispatcher.infrastructure.db.base import DEFAULT_OWNER
from dispatcher.infrastructure.db.models import JsonDict, PlanVersion, Region


class RegionRepository:
    """Участки и их наборы данных."""

    def __init__(self, session: Session, owner_id: str = DEFAULT_OWNER) -> None:
        self._session = session
        self._owner_id = owner_id

    def list(self) -> list[Region]:
        rows = self._session.scalars(
            select(Region)
            .where(Region.owner_id == self._owner_id, Region.deleted_at.is_(None))
            .order_by(Region.id))
        return list(rows)

    def by_key(self, key: str) -> Region | None:
        found: Region | None = self._session.scalar(
            select(Region).where(Region.owner_id == self._owner_id,
                                 Region.key == key,
                                 Region.deleted_at.is_(None)))
        return found

    def save(self, key: str, name: str, payload: JsonDict,
                   office_address: str = "", office_lat: float = 0.0,
                   office_lon: float = 0.0) -> Region:
        """Записывает участок, обновляя существующий."""
        region = self.by_key(key)
        if region is None:
            region = Region(owner_id=self._owner_id, key=key)
            self._session.add(region)
        region.name = name
        region.payload = payload
        region.office_address = office_address
        region.office_lat = office_lat
        region.office_lon = office_lon
        self._session.flush()
        return region


class PlanRepository:
    """Версии плана. Версия неизменяема: правка создаёт следующую."""

    def __init__(self, session: Session, owner_id: str = DEFAULT_OWNER) -> None:
        self._session = session
        self._owner_id = owner_id

    def add_version(self, region_id: int, payload: JsonDict, label: str,
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
        self._session.flush()
        return version

    def current(self, region_id: int) -> PlanVersion | None:
        """Последняя версия плана участка."""
        found: PlanVersion | None = self._session.scalar(
            select(PlanVersion)
            .where(PlanVersion.owner_id == self._owner_id,
                   PlanVersion.region_id == region_id,
                   PlanVersion.deleted_at.is_(None))
            .order_by(PlanVersion.id.desc())
            .limit(1))
        return found

    def history(self, region_id: int, limit: int = 20) -> list[PlanVersion]:
        """Последние версии, новые первыми: из них собирается «шаг назад»."""
        rows = self._session.scalars(
            select(PlanVersion)
            .where(PlanVersion.owner_id == self._owner_id,
                   PlanVersion.region_id == region_id,
                   PlanVersion.deleted_at.is_(None))
            .order_by(PlanVersion.id.desc())
            .limit(limit))
        return list(rows)

    def drop_last(self, region_id: int) -> PlanVersion | None:
        """Шаг назад: последняя версия помечается удалённой.

        Запись остаётся в базе: историю дня не стирают, её сворачивают.
        """
        last = self.current(region_id)
        if last is None:
            return None
        last.deleted_at = datetime.now(UTC)
        self._session.flush()
        return self.current(region_id)


    def drop_all(self, region_id: int) -> int:
        """Сворачивает весь день участка: пришёл новый набор данных.

        Иначе после перезапуска поднялся бы день по прежним заявкам.
        """
        moment = datetime.now(UTC)
        rows = self._session.scalars(
            select(PlanVersion)
            .where(PlanVersion.owner_id == self._owner_id,
                   PlanVersion.region_id == region_id,
                   PlanVersion.deleted_at.is_(None)))
        count = 0
        for row in rows:
            row.deleted_at = moment
            count += 1
        self._session.flush()
        return count
