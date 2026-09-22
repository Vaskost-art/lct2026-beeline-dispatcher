"""Снимок рабочего дня: версия плана, свёрнутая в данные и обратно.

Маршрут хранится последовательностью заявок, а не готовыми временами: при
подъёме он пересчитывается тем же кодом, что и в плане, поэтому расхождение
между сохранённым днём и правилами вылезает сразу, а не переживает запись.

Снимком пользуются оба хранилища - файл на диске и таблица версий, - чтобы
день, поднятый из базы, ничем не отличался от поднятого из файла.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from dispatcher.domain import Engineer, Order, Plan, Route
from dispatcher.services.dataset.errors import DatasetError
from dispatcher.services.dataset.reader import engineer_from_json, order_from_json
from dispatcher.services.dataset.writer import engineer_to_json, order_to_json
from dispatcher.services.metrics import plan_metrics
from dispatcher.services.planning.reasons import diagnose
from dispatcher.services.routing import evaluate_sequence

#: Версия формата снимка. Меняется, когда старую запись уже не поднять.
SNAPSHOT_FORMAT = "dispatcher-saved-plan/1"


@dataclass
class DaySnapshot:
    """Рабочий день участка в виде данных."""

    region_key: str
    region_name: str
    label: str
    orders: list[Order]
    engineers: list[Engineer]
    #: Кто какую заявку везёт: идентификатор бригады -> список заявок по порядку.
    sequences: dict[str, list[str]]
    locked: dict[str, str] = field(default_factory=dict)
    #: Выданное утром оборудование: бригада -> устройство -> сколько.
    issued: dict[str, dict[str, int]] = field(default_factory=dict)
    strategy: str = ""
    solver_status: str = ""
    manual: bool = False
    name: str = ""
    saved_at: str = ""
    #: Заявки, которых не оказалось в наборе при подъёме дня.
    lost: list[str] = field(default_factory=list)


def snapshot_of(region_key: str, region_name: str, label: str, plan: Plan,
                orders: list[Order], engineers: list[Engineer],
                locked: dict[str, str], manual: bool, name: str = "",
                issued: dict[str, dict[str, int]] | None = None) -> DaySnapshot:
    """Собирает снимок из текущей версии дня."""
    return DaySnapshot(
        region_key=region_key,
        region_name=region_name,
        label=label,
        orders=list(orders),
        engineers=list(engineers),
        sequences={route.engineer_id: [stop.order_id for stop in route.stops]
                   for route in plan.routes if route.is_used},
        locked=dict(locked or {}),
        issued={key: dict(value) for key, value in (issued or {}).items()},
        strategy=plan.strategy,
        solver_status=plan.solver_status,
        manual=manual,
        name=name or region_name,
    )


def snapshot_to_json(snapshot: DaySnapshot) -> dict[str, object]:
    """Снимок в данные для записи."""
    return {
        "format": SNAPSHOT_FORMAT,
        "region": snapshot.region_key,
        "region_name": snapshot.region_name,
        "name": snapshot.name or snapshot.region_name,
        "label": snapshot.label,
        "saved_at": (snapshot.saved_at
                     or datetime.now().isoformat(timespec="seconds")),
        "strategy": snapshot.strategy,
        "solver_status": snapshot.solver_status,
        "manual": snapshot.manual,
        "locked": dict(snapshot.locked),
        "issued": {key: dict(value) for key, value in snapshot.issued.items()},
        "orders": [order_to_json(order) for order in snapshot.orders],
        "engineers": [engineer_to_json(engineer) for engineer in snapshot.engineers],
        "routes": [{"engineer": engineer_id, "orders": list(sequence)}
                   for engineer_id, sequence in snapshot.sequences.items()],
    }


def snapshot_from_json(data: dict[str, object]) -> DaySnapshot:
    """Снимок из записанных данных.

    Заявки и бригады разбираются сразу: битую запись лучше опознать здесь,
    чем на попытке собрать по ней маршруты.
    """
    orders = [order_from_json(item) for item in _items(data, "orders")]
    # У выбывшей за день бригады смена схлопнута в точку - это законное
    # состояние сохранённого дня, а не порча записи.
    engineers = [engineer_from_json(item, allow_empty_shift=True)
                 for item in _items(data, "engineers")]
    sequences: dict[str, list[str]] = {}
    for item in _items(data, "routes"):
        engineer_id = str(item.get("engineer") or "")
        listed = item.get("orders")
        if engineer_id and isinstance(listed, list):
            sequences[engineer_id] = [str(oid) for oid in listed]
    known = {order.id for order in orders}
    engineer_ids = {engineer.id for engineer in engineers}
    locked = {key: value
              for key, value in (_mapping(data, "locked")).items()
              if key in known and value in engineer_ids}
    return DaySnapshot(
        region_key=str(data.get("region") or ""),
        region_name=str(data.get("region_name") or ""),
        label=str(data.get("label") or "Восстановлен сохранённый день"),
        orders=orders,
        engineers=engineers,
        sequences=sequences,
        locked=locked,
        issued=_issued(data),
        strategy=str(data.get("strategy") or "restored"),
        solver_status=str(data.get("solver_status") or "RESTORED"),
        manual=bool(data.get("manual", True)),
        name=str(data.get("name") or ""),
        saved_at=str(data.get("saved_at") or ""),
    )


def rebuild(snapshot: DaySnapshot) -> tuple[Plan, dict[str, object], list[str]]:
    """Поднимает план по снимку, пересчитывая маршруты.

    Третьим значением возвращает заявки, которых в наборе не нашлось: день
    поднимется без них, но молчать об этом нельзя.
    """
    by_id = {order.id: order for order in snapshot.orders}
    engineer_by_id = {engineer.id: engineer for engineer in snapshot.engineers}
    routes: list[Route] = []
    lost: list[str] = []
    for engineer_id, sequence in snapshot.sequences.items():
        engineer = engineer_by_id.get(engineer_id)
        if engineer is None:
            continue
        known = [by_id[oid] for oid in sequence if oid in by_id]
        lost.extend(oid for oid in sequence if oid not in by_id)
        route, _ = evaluate_sequence(engineer, known)
        if route is None:
            raise DatasetError(
                f"Сохранённый маршрут «{engineer.name}» не проходит проверку "
                f"ограничений - запись не соответствует данным")
        routes.append(route)
    covered = {route.engineer_id for route in routes}
    routes.extend(Route(engineer_id=engineer.id) for engineer in snapshot.engineers
                  if engineer.id not in covered)

    plan = Plan(routes=routes, strategy=snapshot.strategy,
                solver_status=snapshot.solver_status)
    assigned = {stop.order_id for route in plan.routes for stop in route.stops}
    plan.unassigned = [diagnose(order, snapshot.engineers)
                       for order in snapshot.orders if order.id not in assigned]
    return plan, plan_metrics(plan, snapshot.orders, snapshot.engineers), lost


def _issued(data: dict[str, object]) -> dict[str, dict[str, int]]:
    """Выданное оборудование из записи. Битая запись читается как «не выдано»."""
    value = data.get("issued")
    if not isinstance(value, dict):
        return {}
    result: dict[str, dict[str, int]] = {}
    for engineer_id, items in value.items():
        if isinstance(items, dict):
            result[str(engineer_id)] = {str(name): int(count)
                                        for name, count in items.items()
                                        if isinstance(count, int)}
    return result


def _items(data: dict[str, object], key: str) -> list[dict[str, object]]:
    value = data.get(key)
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _mapping(data: dict[str, object], key: str) -> dict[str, str]:
    value = data.get(key)
    if not isinstance(value, dict):
        return {}
    return {str(k): str(v) for k, v in value.items()}
