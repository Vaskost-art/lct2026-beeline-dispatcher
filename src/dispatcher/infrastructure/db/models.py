"""Таблицы базы: участок, день, версия плана и его содержимое.

Главное решение: **план это неизменяемая версия**. Расчёт не правит план, а
создаёт новую версию со ссылкой на предыдущую. Отсюда бесплатно получаются
история дня и шаг назад, а предпросмотр перепланирования перестаёт быть
временным состоянием в памяти процесса, которое можно перепутать с чужим.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dispatcher.infrastructure.db.base import Base, Owned

#: Содержимое JSON-поля: структура задаётся тем, кто пишет.
type JsonDict = dict[str, object]


class Region(Base, Owned):
    """Участок: три региона задачи плюс загруженные диспетчером наборы."""

    __tablename__ = "regions"
    __table_args__ = (UniqueConstraint("owner_id", "key", name="uq_region_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255))
    office_address: Mapped[str] = mapped_column(Text, default="")
    office_lat: Mapped[float] = mapped_column(Float, default=0.0)
    office_lon: Mapped[float] = mapped_column(Float, default=0.0)
    #: Заявки и исполнители дня. Хранятся целиком: набор приходит одним файлом
    #: и правится только целиком, поэтому дробить его на таблицы незачем.
    payload: Mapped[JsonDict] = mapped_column(JSON, default=dict)

    versions: Mapped[list[PlanVersion]] = relationship(back_populates="region")


class PlanVersion(Base, Owned):
    """Одна версия плана участка.

    Версия неизменяема: любой пересчёт, событие дня или ручная правка создают
    следующую версию со ссылкой на предыдущую.
    """

    __tablename__ = "plan_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("plan_versions.id"),
                                                  default=None)
    #: Что породило эту версию: расчёт, событие дня, ручное переназначение.
    label: Mapped[str] = mapped_column(String(255), default="")
    strategy: Mapped[str] = mapped_column(String(64), default="")
    solver_status: Mapped[str] = mapped_column(String(64), default="")
    solve_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    #: План, метрики и сопутствующее, как их отдаёт планировщик.
    payload: Mapped[JsonDict] = mapped_column(JSON, default=dict)
    #: Заявки, закреплённые диспетчером за бригадой на момент версии.
    locked: Mapped[JsonDict] = mapped_column(JSON, default=dict)

    region: Mapped[Region] = relationship(back_populates="versions")


class GeoPoint(Base, Owned):
    """Кэш координат адреса.

    Переезжает из `data/geo_cache.json`: выверенные через Nominatim координаты
    собирались один раз и терять их нельзя.
    """

    __tablename__ = "geo_points"
    __table_args__ = (UniqueConstraint("address_key", name="uq_geo_address"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    address_key: Mapped[str] = mapped_column(String(512), index=True)
    lat: Mapped[float | None] = mapped_column(Float, default=None)
    lon: Mapped[float | None] = mapped_column(Float, default=None)
    source: Mapped[str] = mapped_column(String(64), default="")
    query: Mapped[str] = mapped_column(Text, default="")


class SavedDay(Base, Owned):
    """Сохранённый рабочий день: диспетчер закрывает сервис и возвращается."""

    __tablename__ = "saved_days"
    __table_args__ = (UniqueConstraint("owner_id", "region_key", "name",
                                       name="uq_saved_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    region_key: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                      default=None)
    payload: Mapped[JsonDict] = mapped_column(JSON, default=dict)
