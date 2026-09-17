"""Что сервис принимает на вход.

Проверка идёт на границе: сюда приходит то, что прислал браузер, и
дальше в сервисы уходят уже проверенные значения.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from dispatcher.domain import SKILL_EMERGENCY
from dispatcher.services.planning.costs import DEFAULT_TIME_LIMIT_SEC


class PlanRequest(BaseModel):
    region: str
    strategy: Literal["baseline", "greedy", "optimized"] = "optimized"
    time_limit_sec: int = Field(DEFAULT_TIME_LIMIT_SEC, ge=1, le=120)
    # True — начать день с чистого листа: снять закрепления, вернуть исходные
    # заявки и смены. По умолчанию пересчёт сохраняет решения диспетчера.
    reset: bool = False


class ExplainRequest(BaseModel):
    region: str
    order_id: str


class NewOrderModel(BaseModel):
    id: str = "URGENT-1"
    lat: float
    lon: float
    address: str = "Адрес не указан"
    district: str = ""
    duration_min: int = Field(90, ge=5, le=480)
    window_start: str = "14:00"
    window_end: str = "16:00"
    required_skill: str = SKILL_EMERGENCY
    required_vehicle: str | None = None


class ReplanRequest(BaseModel):
    region: str
    kind: Literal["urgent_order", "cancel_order", "engineer_unavailable",
                  "engineer_delayed"]
    at: str = "13:00"
    order_id: str | None = None
    engineer_id: str | None = None
    delay_min: int = Field(45, ge=5, le=480)
    new_order: NewOrderModel | None = None
    mode: Literal["minimal", "full"] = "minimal"
    apply: bool = False
    time_limit_sec: int = Field(DEFAULT_TIME_LIMIT_SEC, ge=1, le=120)


class ReassignRequest(BaseModel):
    region: str
    order_id: str
    engineer_id: str | None = None       # None = снять заявку с исполнителя


class AdjustOrderRequest(BaseModel):
    """Ручные правки диспетчера по одной заявке: закрепление и приоритет."""

    region: str
    order_id: str
    # "" или None — снять закрепление; иначе id исполнителя
    lock_to: str | None = None
    set_lock: bool = False                  # трогать ли закрепление вообще
    priority: Literal["Обычная", "Срочная"] | None = None
    time_limit_sec: int = Field(DEFAULT_TIME_LIMIT_SEC, ge=1, le=120)


class RegionRequest(BaseModel):
    region: str


class SavePlanRequest(BaseModel):
    region: str
    name: str = ""


# --- справочники и сценарии --------------------------------------------------
