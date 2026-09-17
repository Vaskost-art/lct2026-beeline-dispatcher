"""Сценарий участка: заявки и бригады на один рабочий день."""
from __future__ import annotations

from dataclasses import dataclass, field

from dispatcher.domain import norms
from dispatcher.domain.catalog import PRIORITY_URGENT
from dispatcher.domain.models import Engineer, Order


@dataclass
class Scenario:
    """Один район на один рабочий день — готовый вход для планировщика."""

    region_key: str
    region_name: str
    orders: list[Order] = field(default_factory=list)
    engineers: list[Engineer] = field(default_factory=list)
    cancelled_ids: list[str] = field(default_factory=list)
    geo_report: dict[str, object] = field(default_factory=dict)
    duplicate_ids: list[str] = field(default_factory=list)
    # строки выгрузки, которые не удалось разобрать: их нет в плане, и знать
    # об этом должен диспетчер, а не только автор кода
    skipped_rows: list[dict[str, str]] = field(default_factory=list)
    # Офис участка: там бригада получает оборудование и начинает день.
    office_address: str = ""
    office_lat: float = 0.0
    office_lon: float = 0.0

    @property
    def order_by_id(self) -> dict[str, Order]:
        return {o.id: o for o in self.orders}

    @property
    def engineer_by_id(self) -> dict[str, Engineer]:
        return {e.id: e for e in self.engineers}

    def summary(self) -> dict[str, object]:
        skills = {s: 0 for s in norms.SKILL_BY_TYPE_BK.values()}
        for o in self.orders:
            skills[o.required_skill] = skills.get(o.required_skill, 0) + 1
        vehicles: dict[str, int] = {}
        for e in self.engineers:
            vehicles[e.vehicle] = vehicles.get(e.vehicle, 0) + 1
        return {
            "region_key": self.region_key,
            "region_name": self.region_name,
            "orders": len(self.orders),
            "engineers": len(self.engineers),
            "urgent": sum(1 for o in self.orders if o.priority == PRIORITY_URGENT),
            "with_vehicle_requirement": sum(1 for o in self.orders if o.required_vehicle),
            "cancelled_in_fact": len(self.cancelled_ids),
            "orders_by_skill": skills,
            "engineers_by_vehicle": vehicles,
            "total_work_hours": round(sum(o.duration_min for o in self.orders) / 60, 1),
            "geocoding": self.geo_report,
            "duplicate_ids": self.duplicate_ids,
            "skipped_rows": self.skipped_rows,
        }
