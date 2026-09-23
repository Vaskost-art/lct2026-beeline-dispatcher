"""Что сервис принимает на вход.

Проверка идёт на границе: сюда приходит то, что прислал браузер, и
дальше в сервисы уходят уже проверенные значения.
"""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from dispatcher.domain import SKILL_EMERGENCY
from dispatcher.services.planning.costs import DEFAULT_TIME_LIMIT_SEC

#: Длина строковых полей запроса: номер заявки на 60 МБ разбирался
#: 37 секунд и возвращался целиком в тексте ошибки.
Key = Annotated[str, Field(max_length=100)]
Text = Annotated[str, Field(max_length=300)]


class PlanRequest(BaseModel):
    region: Key
    strategy: Literal["baseline", "greedy", "optimized"] = "optimized"
    time_limit_sec: int = Field(DEFAULT_TIME_LIMIT_SEC, ge=1, le=DEFAULT_TIME_LIMIT_SEC)
    # True - начать день с чистого листа: снять закрепления, вернуть исходные
    # заявки и смены. По умолчанию пересчёт сохраняет решения диспетчера.
    reset: bool = False


class ExplainRequest(BaseModel):
    region: Key
    order_id: Key


class NewOrderModel(BaseModel):
    id: Key = "URGENT-1"
    lat: float
    lon: float
    address: Text = "Адрес не указан"
    district: Text = ""
    duration_min: int = Field(90, ge=5, le=480)
    window_start: Key = "14:00"
    window_end: Key = "16:00"
    required_skill: Key = SKILL_EMERGENCY
    required_vehicle: Key | None = None


class ReplanRequest(BaseModel):
    region: Key
    kind: Literal["urgent_order", "cancel_order", "engineer_unavailable",
                  "engineer_delayed"]
    at: Key = "13:00"
    order_id: Key | None = None
    engineer_id: Key | None = None
    delay_min: int = Field(45, ge=5, le=480)
    new_order: NewOrderModel | None = None
    mode: Literal["minimal", "full"] = "minimal"
    apply: bool = False
    time_limit_sec: int = Field(DEFAULT_TIME_LIMIT_SEC, ge=1, le=DEFAULT_TIME_LIMIT_SEC)


class ReassignRequest(BaseModel):
    region: Key
    order_id: Key
    engineer_id: Key | None = None       # None = снять заявку с исполнителя


class AdjustOrderRequest(BaseModel):
    """Ручные правки диспетчера по одной заявке: закрепление и приоритет."""

    region: Key
    order_id: Key
    # "" или None - снять закрепление; иначе id исполнителя
    lock_to: Key | None = None
    set_lock: bool = False                  # трогать ли закрепление вообще
    priority: Literal["Обычная", "Срочная"] | None = None
    time_limit_sec: int = Field(DEFAULT_TIME_LIMIT_SEC, ge=1, le=DEFAULT_TIME_LIMIT_SEC)


class OrderStatusRequest(BaseModel):
    """Диспетчер отмечает, что с заявкой происходит сейчас."""

    region: Key
    order_id: Key
    status: Literal["Отправлено", "В пути", "Выполняется", "Завершено",
                    "Отменена"]


class EquipmentTransferRequest(BaseModel):
    """Передача оборудования между бригадами в течение дня."""

    region: Key
    source: Key
    target: Key
    item: Key
    count: int = Field(1, ge=1, le=20)


class RegionRequest(BaseModel):
    region: Key


class SavePlanRequest(BaseModel):
    region: Key
    name: Text = ""


# --- справочники и сценарии --------------------------------------------------
