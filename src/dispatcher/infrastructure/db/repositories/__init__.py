"""Репозитории: единственное место, где живёт обращение к базе.

Сервисы получают репозиторий снаружи и про SQLAlchemy ничего не знают. Ни
одна выборка не возвращает удалённые записи: физического удаления в проекте
нет, вместо него проставляется `deleted_at`.
"""
from dispatcher.infrastructure.db.repositories.cache import (
    GeoRepository,
    SavedDayRepository,
)
from dispatcher.infrastructure.db.repositories.regions import (
    PlanRepository,
    RegionRepository,
)

__all__ = ["GeoRepository", "PlanRepository", "RegionRepository",
           "SavedDayRepository"]
