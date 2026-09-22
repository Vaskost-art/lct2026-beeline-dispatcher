"""Кэш координат и сохранённые дни: то, что переживает перезапуск само по себе."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from dispatcher.infrastructure.db.base import DEFAULT_OWNER
from dispatcher.infrastructure.db.models import GeoPoint, JsonDict, SavedDay


class GeoRepository:
    """Кэш координат адресов."""

    def __init__(self, session: Session, owner_id: str = DEFAULT_OWNER) -> None:
        self._session = session
        self._owner_id = owner_id

    def all(self) -> dict[str, dict[str, object]]:
        rows = self._session.scalars(
            select(GeoPoint).where(GeoPoint.deleted_at.is_(None)))
        return {
            row.address_key: {"lat": row.lat, "lon": row.lon,
                              "source": row.source, "query": row.query}
            for row in rows
        }

    def put(self, address_key: str, lat: float | None, lon: float | None,
                  source: str = "", query: str = "") -> None:
        point = self._session.scalar(
            select(GeoPoint).where(GeoPoint.address_key == address_key))
        if point is None:
            point = GeoPoint(owner_id=self._owner_id, address_key=address_key)
            self._session.add(point)
        point.lat, point.lon = lat, lon
        point.source, point.query = source, query
        self._session.flush()


class SavedDayRepository:
    """Сохранённые рабочие дни."""

    def __init__(self, session: Session, owner_id: str = DEFAULT_OWNER) -> None:
        self._session = session
        self._owner_id = owner_id

    def save(self, region_key: str, name: str, payload: JsonDict) -> SavedDay:
        day = self.get(region_key, name)
        if day is None:
            day = SavedDay(owner_id=self._owner_id, region_key=region_key, name=name)
            self._session.add(day)
        day.payload = payload
        day.saved_at = datetime.now(UTC)
        self._session.flush()
        return day

    def get(self, region_key: str, name: str = "") -> SavedDay | None:
        found: SavedDay | None = self._session.scalar(
            select(SavedDay).where(SavedDay.owner_id == self._owner_id,
                                   SavedDay.region_key == region_key,
                                   SavedDay.name == name,
                                   SavedDay.deleted_at.is_(None)))
        return found

    def list(self) -> list[SavedDay]:
        rows = self._session.scalars(
            select(SavedDay)
            .where(SavedDay.owner_id == self._owner_id,
                   SavedDay.deleted_at.is_(None))
            .order_by(SavedDay.saved_at.desc()))
        return list(rows)
