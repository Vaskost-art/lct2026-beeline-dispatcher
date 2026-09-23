"""Вытеснение обычной заявки срочной.

Авария может подвинуть уже назначенные работы: заказчик прямо сказал,
что срочные заявки вытесняют обычные.
"""
from __future__ import annotations

from dispatcher.domain import (
    PRIORITY_HIGH,
    PRIORITY_NORMAL,
    PRIORITY_URGENT,
    Engineer,
    Order,
    Route,
)
from dispatcher.services.equipment import Stock
from dispatcher.services.planning.costs import ENGINEER_FIXED_COST
from dispatcher.services.routing import evaluate_sequence, insertion_cost

REASON_DISPLACED = "displaced_by_urgent"


def _try_insert(engineer: Engineer, route: Route, by_id: dict[str, Order],
                order: Order, first_free: int) -> tuple[float, Route] | None:
    """Лучшая допустимая вставка заявки в маршрут после замороженного префикса."""
    best: tuple[float, Route] | None = None
    for position in range(first_free, len(route.stops) + 1):
        ok, delta, new_route = insertion_cost(engineer, route, by_id, order, position)
        if ok and new_route is not None and (best is None or delta < best[0]):
            best = (delta, new_route)
    return best


MAX_DISPLACED = 3          # сколько обычных заявок готовы сдвинуть ради аварии


def _place_urgent_with_displacement(
        order: Order, routes: dict[str, Route], engineers: list[Engineer],
        by_id: dict[str, Order], frozen: dict[str, list[str]],
        now: int, stock: Stock | None = None,
        deadline: int | None = None) -> tuple[str, list[Order]] | None:
    """Освобождает место под срочную заявку, сдвигая обычные.

    ТЗ: «Срочная заявка имеет более высокий приоритет при перепланировании».
    Если авария не встаёт в маршрут обычной вставкой, мы снимаем из маршрута
    минимальное число ещё не начатых обычных заявок — столько, сколько нужно,
    чтобы авария поместилась, но не больше MAX_DISPLACED. Снятые заявки затем
    пытаемся передать другим исполнителям; те, кому места не нашлось,
    возвращаются диспетчеру с явной причиной.

    Возвращает (engineer_id, список так и не пристроенных заявок) либо None,
    если места не нашлось даже с вытеснением. `stock` — остаток оборудования
    в сумках: брать заявку может только бригада, у которой нужное устройство
    с собой, и вытеснение этот учёт ведёт само.

    `deadline` — не позже какого момента бригада должна приехать на аварию.
    Организаторы задали ориентир реакции 1-2 часа, и место, найденное позже,
    не годится. Уступает место прежде всего ремонт, подключение - только если
    иначе никак: порядок постановщика «Авария → Подключение → Ремонт».
    """
    best: tuple[float, str, Route, list[Order]] | None = None

    for engineer in engineers:
        if not engineer.can_do(order):
            continue
        if stock is not None and not stock.can_take(engineer.id, order):
            continue
        route = routes[engineer.id]
        first_free = len(frozen.get(engineer.id, []))
        current = [by_id[s.order_id] for s in route.stops]

        for position in range(first_free, len(current) + 1):
            sequence = list(current)
            victims: list[Order] = []
            while True:
                candidate = sequence[:position] + [order] + sequence[position:]
                new_route, _ = evaluate_sequence(engineer, candidate)
                if new_route is not None:
                    if deadline is not None and new_route.stops[position].arrival > deadline:
                        # Приезд определяют визиты до места вставки, а они не
                        # меняются: снимать заявки дальше бесполезно.
                        break
                    # стоимость: прирост пробега плюс плата за каждую сдвинутую
                    # заявку — так вытесняем как можно меньше и как можно дешевле;
                    # подключение отдаётся дороже ремонта
                    cost = ((new_route.total_km - route.total_km)
                            + 10.0 * len(victims)
                            + 15.0 * sum(1 for v in victims if v.priority == PRIORITY_HIGH)
                            + sum(v.duration_min for v in victims) / 60.0)
                    if best is None or cost < best[0]:
                        best = (cost, engineer.id, new_route, victims)
                    break

                # снимаем первую обычную заявку после места вставки: сначала
                # ремонт, подключение - только если ремонта не осталось
                tail = range(position, len(sequence))
                removable = next(
                    (i for i in tail if sequence[i].priority == PRIORITY_NORMAL),
                    next((i for i in tail if sequence[i].priority != PRIORITY_URGENT),
                         None),
                )
                if removable is None or len(victims) >= MAX_DISPLACED:
                    break
                victims.append(sequence.pop(removable))

    if best is None:
        return None

    _, engineer_id, new_route, victims = best
    routes[engineer_id] = new_route
    if stock is not None:
        for victim in victims:
            stock.release(engineer_id, victim)
        stock.take(engineer_id, order)

    # вытесненные заявки пробуем передать другим исполнителям
    homeless: list[Order] = []
    for victim in victims:
        if victim.window_end < now:
            homeless.append(victim)
            continue
        placed: tuple[float, str, Route] | None = None
        for engineer in engineers:
            if not engineer.can_do(victim):
                continue
            if stock is not None and not stock.can_take(engineer.id, victim):
                continue
            route = routes[engineer.id]
            first_free = len(frozen.get(engineer.id, []))
            attempt = _try_insert(engineer, route, by_id, victim, first_free)
            if attempt is None:
                continue
            delta, candidate_route = attempt
            score = delta + (ENGINEER_FIXED_COST / 1000.0
                             if not route.is_used else 0.0)
            if placed is None or score < placed[0]:
                placed = (score, engineer.id, candidate_route)
        if placed is not None:
            routes[placed[1]] = placed[2]
            if stock is not None:
                stock.take(placed[1], victim)
        else:
            homeless.append(victim)

    return engineer_id, homeless


def _resequence_with(engineer: Engineer, route: Route, by_id: dict[str, Order],
                     order: Order, first_free: int,
                     deadline: int | None = None) -> tuple[float, Route] | None:
    """Пересобирает незамороженный хвост маршрута, чтобы вместить заявку.

    Обычная вставка сохраняет порядок уже назначенных заявок, и этого часто
    не хватает: новая заявка не влезает между двумя соседними визитами, хотя
    весь хвост можно просто переставить по времени окон. Здесь мы делаем ровно
    то, что сделал бы диспетчер вручную, — раскладываем оставшиеся заявки
    по возрастанию окна и пробуем поставить новую в каждую позицию.

    `deadline` - для аварии: годятся только варианты, где бригада приезжает
    не позже этого момента.
    """
    current = [by_id[s.order_id] for s in route.stops]
    head, tail = current[:first_free], current[first_free:]
    ordered = sorted(tail, key=lambda o: (o.window_start, o.window_end))

    best: tuple[float, Route] | None = None
    for position in range(len(ordered) + 1):
        candidate = head + ordered[:position] + [order] + ordered[position:]
        new_route, _ = evaluate_sequence(engineer, candidate)
        if new_route is None:
            continue
        if deadline is not None and new_route.stops[len(head) + position].arrival > deadline:
            continue
        delta = new_route.total_km - route.total_km
        if best is None or delta < best[0]:
            best = (delta, new_route)
    return best
