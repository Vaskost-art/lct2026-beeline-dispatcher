"""Состояние заявок в течение смены.

Организаторы: факт выполнения или отмены фиксирует диспетчер со слов
бригады, закрытые заявки в дальнейшее планирование не включаются.

Отсюда два правила, которыми пользуются перепланирование и ручные правки:
закрытую заявку не планируют заново, а начатую не снимают с бригады.
"""
from __future__ import annotations

from dataclasses import replace

from dispatcher.domain import (
    CLOSED_STATUSES,
    STARTED_STATUSES,
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_SENT,
    Engineer,
    Order,
    Plan,
)
from dispatcher.services.routing import evaluate_sequence


def status_of(order_id: str, statuses: dict[str, str]) -> str:
    """Статус заявки. Не отмеченная заявка считается отправленной."""
    return statuses.get(order_id) or STATUS_SENT


def is_closed(order_id: str, statuses: dict[str, str]) -> bool:
    """Работа закончена или отменена: планировать больше нечего."""
    return status_of(order_id, statuses) in CLOSED_STATUSES


def is_started(order_id: str, statuses: dict[str, str]) -> bool:
    """Бригада уже в пути или на адресе: снимать такую заявку нельзя."""
    return status_of(order_id, statuses) in STARTED_STATUSES


def plannable(orders: list[Order], statuses: dict[str, str]) -> list[Order]:
    """Заявки, которые ещё нужно куда-то ставить.

    Отменённые уходят из дня совсем; завершённые остаются в плане на своих
    местах, но заново не распределяются - это делает `frozen_by_status`.
    """
    return [order for order in orders
            if status_of(order.id, statuses) != STATUS_CANCELLED]


def frozen_by_status(plan: Plan, statuses: dict[str, str]) -> dict[str, list[str]]:
    """Что нельзя трогать: начатое и завершённое, по каждой бригаде.

    Замораживается префикс маршрута - от начала и до последней тронутой
    заявки включительно. Иначе выполненная третья заявка осталась бы на
    месте, а первая и вторая уехали бы после неё.
    """
    frozen: dict[str, list[str]] = {}
    for route in plan.routes:
        kept: list[str] = []
        last_touched = -1
        for position, stop in enumerate(route.stops):
            status = status_of(stop.order_id, statuses)
            if status in STARTED_STATUSES or status == STATUS_DONE:
                last_touched = position
        if last_touched < 0:
            continue
        for stop in route.stops[:last_touched + 1]:
            if status_of(stop.order_id, statuses) != STATUS_CANCELLED:
                kept.append(stop.order_id)
        if kept:
            frozen[route.engineer_id] = kept
    return frozen


def day_progress(orders: list[Order], statuses: dict[str, str]) -> dict[str, int]:
    """Сколько заявок закрыто, отменено и в работе: ход смены."""
    counts = {"done": 0, "cancelled": 0, "in_progress": 0, "sent": 0}
    for order in orders:
        status = status_of(order.id, statuses)
        if status == STATUS_DONE:
            counts["done"] += 1
        elif status == STATUS_CANCELLED:
            counts["cancelled"] += 1
        elif status in STARTED_STATUSES:
            counts["in_progress"] += 1
        else:
            counts["sent"] += 1
    return counts


def settle_day(plan: Plan, orders: list[Order], engineers: list[Engineer],
               locked: dict[str, str],
               statuses: dict[str, str]) -> tuple[list[Order], list[Engineer], dict[str, str]]:
    """Вход для пересчёта всего дня, когда смена уже идёт.

    Кнопка «Собрать заново» и смена приоритета пересчитывают день целиком,
    и раньше они не знали об отметках хода работ: завершённую заявку
    раздавали другой бригаде, отменённую возвращали в план. Теперь:
    отменённые уходят из расчёта, начатые и завершённые остаются за своими
    бригадами, а правило «к новому заданию не раньше события» снимается -
    при полном пересчёте события нет, и оно выпускало бригады на весь день
    не раньше момента прошлого события.

    Возвращает заявки, бригады и закрепления для решателя. Закрепления по
    отметкам производные: в версию дня их класть не нужно.
    """
    holder = {stop.order_id: route.engineer_id
              for route in plan.routes for stop in route.stops}
    pinned = dict(locked)
    for order_id, holder_id in holder.items():
        if is_started(order_id, statuses) or status_of(order_id, statuses) == STATUS_DONE:
            pinned[order_id] = holder_id
    fresh = [replace(engineer, resume_after=0, resume_at=0, en_route_to="")
             for engineer in engineers]
    return plannable(orders, statuses), fresh, pinned


def drop_cancelled(plan: Plan, order_id: str, orders: list[Order],
                   engineers: list[Engineer]) -> Plan:
    """План без отменённой заявки: маршрут её бригады пересчитан.

    Отменённая заявка уходит из дня сразу, а не при следующем событии: иначе
    она висела в маршруте, ведомости и счётчиках, а список изменений первого
    события писал про неё «снята с плана». Маршрут пересчитывается, а не
    просто теряет остановку: следующий визит теперь едет из предыдущей
    точки, и пробег обязан это отражать.
    """
    by_id = {order.id: order for order in orders}
    crew_by_id = {engineer.id: engineer for engineer in engineers}
    routes = []
    for route in plan.routes:
        if all(stop.order_id != order_id for stop in route.stops):
            routes.append(route)
            continue
        rest = [by_id[s.order_id] for s in route.stops if s.order_id != order_id]
        rebuilt, _ = evaluate_sequence(crew_by_id[route.engineer_id], rest)
        routes.append(rebuilt if rebuilt is not None else route)
    return Plan(routes=routes, strategy=plan.strategy, solver_status=plan.solver_status,
                unassigned=[u for u in plan.unassigned if u.order_id != order_id],
                solve_seconds=plan.solve_seconds)
