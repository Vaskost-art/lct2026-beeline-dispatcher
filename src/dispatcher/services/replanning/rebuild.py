"""Пересборка остатка дня: весь день после события заново, кроме начатого."""
from __future__ import annotations

import time

from dispatcher.domain import Engineer, Order, Plan
from dispatcher.services.planning.optimizer import solve_optimized
from dispatcher.services.replanning.emergency import credit_gave_way, deadline_for
from dispatcher.services.replanning.events import ReplanEvent

#: Предел пересборки остатка дня. Предпросмотр события ждут у экрана:
#: обычно пересборка укладывается в 12-45 с, но на Юго-востоке авария в 13:00
#: считалась все 300 с предохранителя. minimal: минута на всё, в редких долгих
#: случаях результат зависит от скорости машины; поднимать, если расчёт
#: перенесут в фон с уведомлением.
EVENT_TIME_LIMIT_SEC = 60


def rebuild_rest(current: Plan, orders: list[Order], engineers: list[Engineer],
                 event: ReplanEvent, now: int, frozen: dict[str, list[str]],
                 time_limit_sec: int, issued: dict[str, dict[str, int]] | None,
                 locked: dict[str, str] | None) -> tuple[Plan, dict[str, list[str]]]:
    """Новый план на остаток дня и то, что в нём осталось замороженным.

    Решатель соблюдает то же, что и точечная правка: сумку бригады, закрепления
    диспетчера и срок приезда на аварию, поступившую этим событием.
    """
    # Срок приезда - только у аварии, поступившей этим событием: утренние
    # аварии тянутся к началу окна прежней ценой, и чужая пересборка не
    # должна приписывать их потерю «аварии».
    limit = min(time_limit_sec, EVENT_TIME_LIMIT_SEC)
    started = time.monotonic()
    arrived = event.new_order
    due = deadline_for(arrived, now) if arrived is not None else None
    deadlines = {arrived.id: due} if arrived is not None and due else {}
    plan = solve_optimized(orders, engineers, time_limit_sec=limit,
                           locked=locked or None, frozen=frozen,
                           deadlines=deadlines, issued=issued)
    credit_gave_way(current, plan, deadlines)
    # Если модель с замороженными префиксами оказалась неразрешимой,
    # повторяем без заморозки: лучше перестроенный день, чем пустой план.
    if plan.assigned_count == 0 and current.assigned_count > 0:
        # Запасной расчёт укладывается в тот же бюджет и держит срок аварии.
        left = max(5, int(limit - (time.monotonic() - started)))
        plan = solve_optimized(orders, engineers, time_limit_sec=left,
                               locked=locked or None, deadlines=deadlines,
                               issued=issued)
        plan.solver_status += "_NO_FREEZE_FALLBACK"
        return plan, {}
    return plan, frozen


def lost_by_rebuild(current: Plan, rebuilt: Plan, orders: list[Order]) -> list[str]:
    """Заявки, которые были в плане и после пересборки остались без бригады."""
    alive = {order.id for order in orders}
    placed = {stop.order_id for route in rebuilt.routes for stop in route.stops}
    return sorted(stop.order_id for route in current.routes for stop in route.stops
                  if stop.order_id in alive and stop.order_id not in placed)
