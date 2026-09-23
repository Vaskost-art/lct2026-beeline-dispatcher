"""Авария, поступившая днём: срок приезда, реакция, цена ожидания.

Организаторы (22.09): авария имеет максимальный приоритет и может
перестроить остаток дня; для сетевой аварии допустимо закладывать время
реакции 1-2 часа. Порядок при нехватке людей: авария, подключение, ремонт.
Поэтому если иначе к аварии в срок не успеть, ремонт уступает ей место.
"""
from __future__ import annotations

from dispatcher.domain import PRIORITY_URGENT, Engineer, Order, Plan, Route, Unassigned
from dispatcher.domain.norms import REACTION_TARGET_MIN
from dispatcher.services.equipment import Stock
from dispatcher.services.planning.costs import URGENT_DELAY_COST_PER_MIN
from dispatcher.services.replanning.displacement import (
    REASON_DISPLACED,
    _place_urgent_with_displacement,
    _resequence_with,
)
from dispatcher.services.replanning.events import KIND_URGENT, ReplanEvent

#: Цена километра в целевой функции решателя: дуга весит метры пробега.
KM_COST = 1000




def reaction(plan: Plan, event: ReplanEvent) -> dict[str, object] | None:
    """Через сколько бригада приедет на аварию, поступившую днём.

    Считается от поступления до прибытия, а не до начала работ: ожидание
    открытия окна - не задержка реакции, бригада уже на месте. Для
    обычной заявки и для аварии, которой не нашлось бригады, ответа нет.
    """
    order = event.new_order
    if event.kind != KIND_URGENT or order is None or order.priority != PRIORITY_URGENT:
        return None
    for route in plan.routes:
        for stop in route.stops:
            if stop.order_id == order.id:
                minutes = stop.arrival - event.at
                # «В срок» судится тем же сроком, по которому ставили аварию.
                due = deadline_for(order, event.at)
                return {"engineer_id": route.engineer_id, "minutes": minutes,
                        "target_min": REACTION_TARGET_MIN,
                        "within": due is None or stop.arrival <= due}
    return None


def describe_reaction(info: dict[str, object]) -> str:
    """Строка для рассказа о событии."""
    minutes = int(str(info["minutes"]))
    spent = f"{minutes // 60} ч {minutes % 60} мин" if minutes >= 60 else f"{minutes} мин"
    verdict = ("в пределах ориентира 1-2 часа" if info["within"]
               else "дольше ориентира 1-2 часа: стоит проверить, нельзя ли "
                    "снять с ближней бригады обычную заявку вручную")
    return (f"«{info['engineer_id']}» прибудет на аварию через {spent} после "
            f"её поступления - {verdict}.")


def stuck_emergencies(plan: Plan, orders: list[Order]) -> list[str]:
    """Срочные заявки, не вставшие точечной правкой, и что с этим делать.

    Это решение диспетчера, а не тупик: называем причину из диагностики -
    она может быть любой, от нехватки навыка до занятого окна, - и говорим,
    чем придётся заплатить за другой режим.
    """
    placed = {stop.order_id for route in plan.routes for stop in route.stops}
    reasons = {item.order_id: item.reason_text for item in plan.unassigned}
    return [f"Срочная заявка {order.id} не размещена точечной правкой. "
            f"{reasons.get(order.id, 'Причина не определена.')} "
            f"Попробуйте режим «Пересобрать остаток дня»: он может найти для "
            f"неё место ценой перестановок в маршрутах и, возможно, снятия "
            f"другой заявки. Решение за диспетчером."
            for order in orders
            if order.priority == PRIORITY_URGENT and order.id not in placed]



def delay_cost(order: Order, route: Route, now: int) -> float:
    """Цена ожидания аварии в километрах при выборе места точечной правкой.

    Минута ожидания стоит столько же, сколько отсрочка утренней аварии в
    решателе (URGENT_DELAY_COST_PER_MIN): без этой цены место выбиралось по
    пробегу и авария уезжала в конец чужого дня. Срок реакции точечная
    правка держит отдельно, вытеснением (`place_in_time`); решатель держит
    его мягкой границей. Для обычной заявки цена нулевая.
    """
    if order.priority != PRIORITY_URGENT:
        return 0.0
    stop = next((item for item in route.stops if item.order_id == order.id), None)
    if stop is None:
        return 0.0
    waited = max(0, stop.start - max(order.window_start, now))
    return waited * URGENT_DELAY_COST_PER_MIN / KM_COST


def deadline_for(order: Order, now: int) -> int | None:
    """Не позже какого момента бригада должна приехать на аварию.

    Отсчёт от поступления или от начала окна, если диспетчер задал его
    позже: приезжать раньше окна бессмысленно.
    """
    if order.priority != PRIORITY_URGENT:
        return None
    return max(order.window_start, now) + REACTION_TARGET_MIN


def place_in_time(order: Order, found: Route, routes: dict[str, Route],
                  engineers: list[Engineer], by_id: dict[str, Order],
                  frozen: dict[str, list[str]], now: int,
                  stock: Stock) -> list[Order] | None:
    """Если место для аварии нашлось позже срока - освободить место раньше.

    Возвращает None, когда найденное место годится или раньше его не найти:
    тогда вызывающая сторона ставит аварию туда. Иначе вытеснение уже
    применено, и возвращаются заявки, которым не нашлось другой бригады.
    """
    deadline = deadline_for(order, now)
    stop = next((item for item in found.stops if item.order_id == order.id), None)
    if deadline is None or stop is None or stop.arrival <= deadline:
        return None
    outcome = _place_urgent_with_displacement(order, routes, engineers, by_id,
                                              frozen, now, stock, deadline=deadline)
    if outcome is not None:
        return outcome[1]
    # Не вышло без перестановки: пересобираем хвост маршрута так, чтобы
    # авария встала раньше. Так же поступает и пересборка дня, только здесь
    # трогается одна бригада, а не все.
    rebuilt = _in_time_by_reordering(order, routes, engineers, by_id, frozen,
                                     deadline, stock)
    return [] if rebuilt else None


def _in_time_by_reordering(order: Order, routes: dict[str, Route],
                           engineers: list[Engineer], by_id: dict[str, Order],
                           frozen: dict[str, list[str]], deadline: int,
                           stock: Stock) -> bool:
    """Ставит аварию в срок перестановкой хвоста одной бригады."""
    best: tuple[float, str, Route] | None = None
    for engineer in engineers:
        if not engineer.can_do(order) or not stock.can_take(engineer.id, order):
            continue
        attempt = _resequence_with(engineer, routes[engineer.id], by_id, order,
                                   len(frozen.get(engineer.id, [])), deadline)
        if attempt is not None and (best is None or attempt[0] < best[0]):
            best = (attempt[0], engineer.id, attempt[1])
    if best is None:
        return False
    routes[best[1]] = best[2]
    stock.take(best[1], order)
    return True


def settle(order: Order, best: tuple[float, str, Route], routes: dict[str, Route],
            engineers: list[Engineer], by_id: dict[str, Order],
            frozen: dict[str, list[str]], now: int, stock: Stock,
            displaced: dict[str, str]) -> None:
    """Ставит заявку на найденное место, а аварию - в срок, если найденное позже."""
    homeless = place_in_time(order, best[2], routes, engineers, by_id, frozen, now, stock)
    if homeless is None:
        routes[best[1]] = best[2]
        stock.take(best[1], order)
        return
    for victim in homeless:
        displaced[victim.id] = order.id


def credit_gave_way(before: Plan, after: Plan, deadlines: dict[str, int]) -> None:
    """Называет заявки, которые после пересборки выпали ради аварии.

    Уступившей считается только заявка, стоявшая до события у той бригады,
    что теперь едет на аварию: остальные выпали по другим причинам, и их
    объясняет общая диагностика.
    """
    rescuers = {route.engineer_id: stop.order_id for route in after.routes
                for stop in route.stops if stop.order_id in deadlines}
    if not rescuers:
        return
    gave_way = {stop.order_id: rescuers[route.engineer_id]
                for route in before.routes if route.engineer_id in rescuers
                for stop in route.stops}
    for index, item in enumerate(after.unassigned):
        if item.order_id in gave_way:
            after.unassigned[index] = Unassigned(
                order_id=item.order_id, reason=REASON_DISPLACED,
                reason_text=f"Уступила место аварии {gave_way[item.order_id]}: её "
                            f"бригада не успевала к аварии в срок (ориентир "
                            f"организаторов - 1-2 часа).")
