"""Режим минимальной правки: чиним день, не перестраивая его целиком."""
from __future__ import annotations

from dispatcher.domain import PRIORITY_URGENT, Engineer, Order, Plan, Route, Unassigned
from dispatcher.services.planning.costs import ENGINEER_FIXED_COST
from dispatcher.services.planning.reasons import diagnose
from dispatcher.services.replanning.displacement import (
    REASON_DISPLACED,
    _place_urgent_with_displacement,
    _resequence_with,
)
from dispatcher.services.replanning.events import KIND_UNAVAILABLE, ReplanEvent
from dispatcher.services.routing import evaluate_sequence, insertion_cost

MODE_MINIMAL = "minimal"
MODE_FULL = "full"

MODE_TITLES = {
    MODE_MINIMAL: "Точечная правка",
    MODE_FULL: "Пересобрать остаток дня",
}

MODE_HINTS = {
    MODE_MINIMAL: "Встроить изменение, не трогая остальные назначения. "
                  "Бригадам не придётся рассылать новые маршруты.",
    MODE_FULL: "Перестроить весь остаток дня заново. Обычно короче по пробегу, "
               "но маршруты изменятся у многих.",
}


def _repair(orders: list[Order], engineers: list[Engineer], current: Plan,
            event: ReplanEvent, now: int,
            frozen: dict[str, list[str]]) -> Plan:
    """Встраивает изменение, не трогая остальные назначения.

    Диспетчеру важнее предсказуемость, чем последние проценты пробега: если
    событие можно отработать точечно, бригады не должны получать новый план
    целиком. Поэтому сначала пробуем починить план вставкой, и только если
    это не удаётся — вызывающая сторона перепланирует остаток дня полностью.
    """
    by_id = {o.id: o for o in orders}
    engineer_by_id = {e.id: e for e in engineers}

    sequences: dict[str, list[Order]] = {}
    orphans: list[Order] = []
    displaced: dict[str, str] = {}      # вытесненная заявка -> срочная заявка

    for route in current.routes:
        engineer = engineer_by_id.get(route.engineer_id)
        if engineer is None:
            continue
        kept: list[Order] = []
        for stop in route.stops:
            order = by_id.get(stop.order_id)
            if order is None:                      # заявка отменена событием
                continue
            started = stop.order_id in frozen.get(route.engineer_id, [])
            if started:
                kept.append(order)
                continue
            # у выбывшего исполнителя всё незапущенное уходит в общий пул
            if (event.kind == KIND_UNAVAILABLE
                    and route.engineer_id == event.engineer_id):
                orphans.append(order)
                continue
            kept.append(order)
        sequences[route.engineer_id] = kept

    # заявка, появившаяся по событию, и всё, что не было назначено раньше
    assigned_ids = {s.order_id for r in current.routes for s in r.stops}
    for order in orders:
        if order.id not in assigned_ids and not any(o.id == order.id for o in orphans):
            orphans.append(order)

    # маршруты, оставшиеся после изъятия
    routes: dict[str, Route] = {}
    for engineer in engineers:
        sequence = sequences.get(engineer.id, [])
        built, _ = evaluate_sequence(engineer, sequence)
        rebuilt: Route | None = built
        if rebuilt is None:
            # Последовательность перестала быть выполнимой — например, бригада
            # задержалась и хвост маршрута больше не помещается в смену.
            # Снимаем заявки с конца по одной, пока остаток не станет
            # выполнимым: так у бригады остаётся максимум работы, а в общий
            # пул уходит только то, что она действительно не успевает.
            prefix_ids = frozen.get(engineer.id, [])
            head = list(sequence)
            dropped: list[Order] = []
            while head:
                if head[-1].id in prefix_ids:
                    break                       # начатое снимать нельзя
                dropped.append(head.pop())
                rebuilt, _ = evaluate_sequence(engineer, head)
                if rebuilt is not None:
                    break
            if rebuilt is None:
                # не помогло даже это: оставляем только начатое
                prefix = [o for o in sequence if o.id in prefix_ids]
                dropped = [o for o in sequence if o.id not in prefix_ids]
                rebuilt, _ = evaluate_sequence(engineer, prefix)
            orphans.extend(dropped)
        routes[engineer.id] = (rebuilt if rebuilt is not None
                               else Route(engineer_id=engineer.id))

    # вставка «сирот»: срочные и ранние окна первыми
    orphans.sort(key=lambda o: (0 if o.priority == PRIORITY_URGENT else 1,
                                o.window_start, o.window_end))
    for order in orphans:
        if order.window_end < now:
            continue
        best: tuple[float, str, Route] | None = None
        for engineer in engineers:
            if not engineer.can_do(order):
                continue
            route = routes[engineer.id]
            first_free = len(frozen.get(engineer.id, []))
            for position in range(first_free, len(route.stops) + 1):
                ok, delta, new_route = insertion_cost(
                    engineer, route, by_id, order, position)
                if not ok:
                    continue
                score = delta + (ENGINEER_FIXED_COST / 1000.0
                                 if not route.is_used else 0.0)
                if new_route is not None and (best is None or score < best[0]):
                    best = (score, engineer.id, new_route)
        if best is not None:
            routes[best[1]] = best[2]
            continue

        # Вставка «как есть» не удалась — пробуем пересобрать хвост маршрута.
        for engineer in engineers:
            if not engineer.can_do(order):
                continue
            route = routes[engineer.id]
            first_free = len(frozen.get(engineer.id, []))
            attempt = _resequence_with(engineer, route, by_id, order, first_free)
            if attempt is None:
                continue
            delta, new_route = attempt
            score = delta + (ENGINEER_FIXED_COST / 1000.0
                             if not route.is_used else 0.0)
            if best is None or score < best[0]:
                best = (score, engineer.id, new_route)
        if best is not None:
            routes[best[1]] = best[2]
            continue

        # Срочная заявка не встала и после пересборки — освобождаем ей место.
        if order.priority == PRIORITY_URGENT:
            outcome = _place_urgent_with_displacement(
                order, routes, engineers, by_id, frozen, now)
            if outcome is not None:
                _, homeless = outcome
                for victim in homeless:
                    displaced[victim.id] = order.id

    plan = Plan(routes=list(routes.values()), strategy="replanned",
                solver_status="MINIMAL_REPAIR")
    assigned = {s.order_id for r in plan.routes for s in r.stops}

    reasons = []
    for o in orders:
        if o.id in assigned:
            continue
        if o.id in displaced:
            reasons.append(Unassigned(
                order_id=o.id, reason=REASON_DISPLACED,
                reason_text=f"Вытеснена срочной заявкой {displaced[o.id]}: "
                            f"освободить место было больше негде. "
                            f"Окно {o.window_text}, требуется навык "
                            f"«{o.required_skill}».",
            ))
        else:
            reasons.append(diagnose(o, engineers))
    plan.unassigned = reasons
    return plan
