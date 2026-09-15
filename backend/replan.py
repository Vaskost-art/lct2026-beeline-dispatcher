"""Перепланирование дня после события (ТЗ п. 2.1 п.6 и п. 2.4.1).

Поддерживаются все три события из справочника ТЗ:
  * появилась срочная заявка;
  * заявка отменена;
  * инженер стал недоступен.

Принцип: прошлое не переписываем. Всё, к чему исполнитель уже приступил
к моменту события, замораживается и остаётся на своём месте; заново
планируется только оставшаяся часть дня. Поэтому новый план можно
показать бригадам, не отзывая их с уже начатых работ.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace

import norms
from domain import Engineer, Order, Plan, Unassigned, hhmm
from domain import Route
from routing import evaluate_sequence, insertion_cost
from solver import (DEFAULT_TIME_LIMIT_SEC, ENGINEER_FIXED_COST, diagnose,
                    solve_optimized)

KIND_URGENT = "urgent_order"
KIND_CANCEL = "cancel_order"
KIND_UNAVAILABLE = "engineer_unavailable"
KIND_DELAYED = "engineer_delayed"

KIND_TITLES = {
    KIND_URGENT: "Появилась срочная заявка",
    KIND_CANCEL: "Заявка отменена",
    KIND_UNAVAILABLE: "Инженер стал недоступен",
    KIND_DELAYED: "Бригада задерживается",
}


@dataclass
class ReplanEvent:
    """Событие переплана: тип, время и предмет."""

    kind: str
    at: int                                   # минуты от полуночи
    order_id: str | None = None               # для отмены
    engineer_id: str | None = None            # для недоступности и задержки
    new_order: Order | None = None            # для срочной заявки
    delay_min: int = 0                        # для задержки, минут

    @property
    def title(self) -> str:
        return KIND_TITLES.get(self.kind, self.kind)

    def describe(self) -> str:
        if self.kind == KIND_URGENT and self.new_order:
            o = self.new_order
            return (f"В {hhmm(self.at)} поступила срочная заявка {o.id}: "
                    f"{o.type_hd}, {o.district}, окно {o.window_text}, "
                    f"{o.duration_min} мин.")
        if self.kind == KIND_CANCEL:
            return f"В {hhmm(self.at)} отменена заявка {self.order_id}."
        if self.kind == KIND_UNAVAILABLE:
            return (f"В {hhmm(self.at)} исполнитель «{self.engineer_id}» "
                    f"выбыл — оставшиеся заявки нужно передать другим.")
        if self.kind == KIND_DELAYED:
            return (f"В {hhmm(self.at)} бригада «{self.engineer_id}» "
                    f"сообщила о задержке на {self.delay_min} мин: весь "
                    f"остаток её маршрута уезжает на это время вперёд.")
        return f"Событие в {hhmm(self.at)}."


@dataclass
class ReplanResult:
    plan: Plan
    diff: dict = field(default_factory=dict)
    narrative: list[str] = field(default_factory=list)
    frozen: dict[str, list[str]] = field(default_factory=dict)
    engineers: list[Engineer] = field(default_factory=list)
    """Состав исполнителей с учётом события: у выбывшего обрезана смена,
    у остальных остаток дня начинается с момента события. Именно против этого
    состава корректно проверять полученный план."""

    orders: list[Order] = field(default_factory=list)
    """Заявки с учётом события: добавленная срочная или без отменённой."""


def _frozen_prefixes(plan: Plan, now: int) -> dict[str, list[str]]:
    """Заявки, к которым уже приступили: менять их нельзя."""
    frozen: dict[str, list[str]] = {}
    for route in plan.routes:
        started = [s.order_id for s in route.stops if s.start <= now]
        if started:
            frozen[route.engineer_id] = started
    return frozen


def apply_event(orders: list[Order], engineers: list[Engineer],
                event: ReplanEvent) -> tuple[list[Order], list[Engineer]]:
    """Возвращает изменённые списки заявок и исполнителей после события."""
    new_orders = list(orders)
    new_engineers = [deepcopy(e) for e in engineers]

    if event.kind == KIND_CANCEL:
        new_orders = [o for o in new_orders if o.id != event.order_id]

    elif event.kind == KIND_URGENT and event.new_order is not None:
        new_orders = new_orders + [event.new_order]

    # Недоступность исполнителя обрабатывается в replan(): там известно,
    # какие работы он уже начал и обязан довести до конца.

    return new_orders, new_engineers


def replan(orders: list[Order], engineers: list[Engineer], current: Plan,
           event: ReplanEvent, mode: str = "minimal",
           time_limit_sec: int = DEFAULT_TIME_LIMIT_SEC) -> ReplanResult:
    """Строит новый план на остаток дня и объясняет, что изменилось.

    mode='minimal' — точечно встроить изменение, не трогая остальные назначения;
    mode='full'    — перепланировать весь остаток дня заново.
    """
    now = event.at
    new_orders, new_engineers = apply_event(orders, engineers, event)

    frozen = _frozen_prefixes(current, now)
    if event.kind == KIND_UNAVAILABLE:
        # Выбывший исполнитель доводит до конца то, к чему уже приступил,
        # и больше ничего не берёт. Обрезать смену ровно моментом события
        # нельзя: начатая работа может заканчиваться позже, и тогда план
        # стал бы противоречивым.
        last_end = now
        route = next((r for r in current.routes
                      if r.engineer_id == event.engineer_id), None)
        if route:
            for stop in route.stops:
                if stop.start <= now:
                    last_end = max(last_end, stop.end)
        for engineer in new_engineers:
            if engineer.id == event.engineer_id:
                # Если исполнитель выбыл ещё до начала смены, конец не должен
                # уехать ниже начала: смена просто становится нулевой.
                engineer.shift_end = max(engineer.shift_start,
                                         min(engineer.shift_end, last_end))
                # Обед укоротившейся смене уже не нужен: бригада не работает
                # весь день, а вычитать из остатка полный перерыв — значит
                # отнять у неё время, которое она реально отработала.
                engineer.break_min = norms.break_minutes(engineer.shift_start,
                                                         engineer.shift_end)
        frozen.setdefault(event.engineer_id, [])

    elif event.kind == KIND_DELAYED:
        # Бригада не выбывает — она сдвигается во времени.
        #
        # Если работы уже начаты, двигать начало смены нельзя: начатый визит
        # стоит раньше и модель станет противоречивой. Поэтому задержку
        # записываем в последний начатый визит — он длится на delay_min
        # дольше, и весь хвост маршрута уезжает ровно на это время.
        # Для бригады, которая ещё не приступала, достаточно сдвинуть
        # начало смены: результат тот же, а модель проще.
        delay = max(0, int(event.delay_min))
        prefix = frozen.get(event.engineer_id) or []
        if prefix:
            last_id = prefix[-1]
            new_orders = [replace(o, duration_min=o.duration_min + delay)
                          if o.id == last_id else o for o in new_orders]
        else:
            for engineer in new_engineers:
                if engineer.id == event.engineer_id:
                    engineer.shift_start = min(
                        max(engineer.shift_start, now + delay),
                        engineer.shift_end)

    frozen_ids = {oid for ids in frozen.values() for oid in ids}

    # Заявки, чьё окно закрылось к моменту события и которые ещё не начаты,
    # спланировать уже нельзя — показываем это явной причиной.
    expired: list[Unassigned] = []
    plannable: list[Order] = []
    for order in new_orders:
        if order.id not in frozen_ids and order.window_end < now:
            expired.append(Unassigned(
                order_id=order.id, reason="window_passed",
                reason_text=f"Временное окно {order.window_text} закрылось "
                            f"до момента события ({hhmm(now)}).",
            ))
        else:
            plannable.append(order)

    # Исполнители, у которых ничего не заморожено, начинают остаток дня «сейчас».
    adjusted: list[Engineer] = []
    for engineer in new_engineers:
        e = deepcopy(engineer)
        if not frozen.get(e.id):
            e.shift_start = max(e.shift_start, min(now, e.shift_end))
        adjusted.append(e)

    if mode == MODE_MINIMAL:
        new_plan = _repair(plannable, adjusted, current, event, now, frozen)
    else:
        new_plan = solve_optimized(plannable, adjusted,
                                   time_limit_sec=time_limit_sec, frozen=frozen)

        # Если модель с замороженными префиксами оказалась неразрешимой,
        # повторяем без заморозки: лучше перестроенный день, чем пустой план.
        if new_plan.assigned_count == 0 and current.assigned_count > 0:
            new_plan = solve_optimized(plannable, adjusted,
                                       time_limit_sec=time_limit_sec)
            new_plan.solver_status += "_NO_FREEZE_FALLBACK"
            frozen = {}

    new_plan.unassigned = [u for u in new_plan.unassigned
                           if u.order_id not in {e.order_id for e in expired}]
    new_plan.unassigned.extend(expired)
    new_plan.strategy = "replanned"

    diff = build_diff(current, new_plan, orders, new_orders, frozen_ids, event)
    diff["mode"] = mode
    diff["mode_title"] = MODE_TITLES.get(mode, mode)

    narrative = describe_diff(diff, event)

    # Если срочная заявка не встала — это решение диспетчера, а не тупик:
    # называем причину и говорим, чем за неё придётся заплатить.
    assigned_ids = {s.order_id for r in new_plan.routes for s in r.stops}
    stuck = [o for o in new_orders
             if o.priority == norms.PRIORITY_URGENT and o.id not in assigned_ids]
    if stuck and mode == MODE_MINIMAL:
        # Причину берём из диагностики, а не придумываем: она может быть
        # любой — от отсутствия навыка до занятого окна.
        reasons = {u.order_id: u.reason_text for u in new_plan.unassigned}
        for order in stuck:
            narrative.append(
                f"Срочная заявка {order.id} не размещена точечной правкой. "
                f"{reasons.get(order.id, 'Причина не определена.')} "
                f"Попробуйте режим «{MODE_TITLES[MODE_FULL]}»: "
                f"он может найти для неё место ценой перестановок в маршрутах "
                f"и, возможно, снятия другой заявки. Решение за диспетчером."
            )

    return ReplanResult(plan=new_plan, diff=diff, narrative=narrative,
                        frozen=frozen, engineers=adjusted, orders=new_orders)


def build_diff(before: Plan, after: Plan, orders_before: list[Order],
               orders_after: list[Order], frozen_ids: set[str],
               event: ReplanEvent) -> dict:
    """Построчное сравнение двух планов: что именно изменилось."""
    ids_before = {o.id for o in orders_before}
    ids_after = {o.id for o in orders_after}

    def positions(plan: Plan) -> dict[str, tuple[str, int]]:
        out: dict[str, tuple[str, int]] = {}
        for route in plan.routes:
            for i, stop in enumerate(route.stops):
                out[stop.order_id] = (route.engineer_id, i)
        return out

    pos_before, pos_after = positions(before), positions(after)
    changes: list[dict] = []

    for order_id in sorted(ids_before | ids_after):
        b = pos_before.get(order_id)
        a = pos_after.get(order_id)

        if order_id not in ids_before:
            status = "added"
        elif order_id not in ids_after:
            status = "cancelled"
        elif order_id in frozen_ids:
            status = "frozen"
        elif b is None and a is None:
            status = "still_unassigned"
        elif b is None:
            status = "rescued"
        elif a is None:
            status = "dropped"
        elif b[0] != a[0]:
            status = "moved"
        elif b[1] != a[1]:
            status = "resequenced"
        else:
            status = "unchanged"

        if status in ("unchanged", "still_unassigned"):
            continue

        changes.append({
            "order_id": order_id,
            "status": status,
            "from_engineer": b[0] if b else None,
            "to_engineer": a[0] if a else None,
            "from_position": b[1] + 1 if b else None,
            "to_position": a[1] + 1 if a else None,
        })

    km_before = {r.engineer_id: r.total_km for r in before.routes}
    km_after = {r.engineer_id: r.total_km for r in after.routes}
    n_before = {r.engineer_id: len(r.stops) for r in before.routes}
    n_after = {r.engineer_id: len(r.stops) for r in after.routes}

    engineer_rows = []
    for engineer_id in sorted(set(km_before) | set(km_after)):
        row = {
            "engineer_id": engineer_id,
            "orders_before": n_before.get(engineer_id, 0),
            "orders_after": n_after.get(engineer_id, 0),
            "km_before": round(km_before.get(engineer_id, 0.0), 2),
            "km_after": round(km_after.get(engineer_id, 0.0), 2),
        }
        row["orders_delta"] = row["orders_after"] - row["orders_before"]
        row["km_delta"] = round(row["km_after"] - row["km_before"], 2)
        if row["orders_delta"] or abs(row["km_delta"]) > 0.05:
            engineer_rows.append(row)

    counts: dict[str, int] = {}
    for c in changes:
        counts[c["status"]] = counts.get(c["status"], 0) + 1

    return {
        "event": {"kind": event.kind, "title": event.title, "at": hhmm(event.at),
                  "description": event.describe()},
        "changes": changes,
        "counts": counts,
        "engineers": engineer_rows,
        "totals": {
            "used_engineers_before": before.used_engineers,
            "used_engineers_after": after.used_engineers,
            "total_km_before": round(before.total_km, 2),
            "total_km_after": round(after.total_km, 2),
            "assigned_before": before.assigned_count,
            "assigned_after": after.assigned_count,
        },
    }


STATUS_TEXT = {
    "added": "добавлена в план",
    "cancelled": "снята с плана",
    "moved": "передана другому исполнителю",
    "resequenced": "изменила место в маршруте",
    "dropped": "выпала из плана",
    "rescued": "вернулась в план",
    "frozen": "не тронута — работы уже начаты",
}


def describe_diff(diff: dict, event: ReplanEvent) -> list[str]:
    """Человекочитаемый рассказ о переплане."""
    lines = [event.describe()]
    if diff.get("mode_title"):
        lines.append(f"Режим перепланирования: {diff['mode_title'].lower()}.")
    counts = diff["counts"]
    totals = diff["totals"]

    parts = []
    for key in ("added", "cancelled", "moved", "resequenced", "rescued", "dropped"):
        if counts.get(key):
            parts.append(f"{STATUS_TEXT[key]}: {counts[key]}")
    if parts:
        lines.append("Изменения в назначениях — " + "; ".join(parts) + ".")
    else:
        lines.append("Назначения не изменились: событие удалось обработать "
                     "без перестановок.")

    if counts.get("frozen"):
        lines.append(f"Заявок, к которым бригады уже приступили и которые "
                     f"остались нетронутыми: {counts['frozen']}.")

    km_delta = totals["total_km_after"] - totals["total_km_before"]
    eng_delta = totals["used_engineers_after"] - totals["used_engineers_before"]
    lines.append(
        f"Итог: назначено {totals['assigned_after']} "
        f"(было {totals['assigned_before']}), "
        f"исполнителей {totals['used_engineers_after']} "
        f"(было {totals['used_engineers_before']}, "
        f"{eng_delta:+d}), пробег {totals['total_km_after']:.1f} км "
        f"(было {totals['total_km_before']:.1f}, {km_delta:+.1f})."
    )
    return lines


def make_urgent_order(order_id: str, lat: float, lon: float, address: str,
                      district: str, duration_min: int, window_start: int,
                      window_end: int, required_skill: str,
                      required_vehicle: str | None = None,
                      type_hd: str | None = None) -> Order:
    """Собирает срочную заявку с полным набором полей (ТЗ п. 2.4.1).

    Тип работ выводится из требуемого навыка, чтобы карточка заявки в
    интерфейсе не противоречила сама себе.
    """
    type_bk = next((bk for bk, skill in norms.SKILL_BY_TYPE_BK.items()
                    if skill == required_skill), "Глобальная проблема")
    defaults = {
        norms.SKILL_EMERGENCY: "Авария",
        norms.SKILL_LOCAL: "Нет линка",
        norms.SKILL_CONNECT: "Заявка на подключение",
    }
    return Order(
        id=order_id, lat=lat, lon=lon, address=address, district=district,
        duration_min=duration_min, window_start=window_start,
        window_end=window_end, priority=norms.PRIORITY_URGENT,
        required_skill=required_skill, required_vehicle=required_vehicle,
        type_bk=type_bk, type_hd=type_hd or defaults.get(required_skill, "Авария"),
        geocode_precision="manual",
    )


# --- режим «минимальная правка» ----------------------------------------------

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
        route, _ = evaluate_sequence(engineer, sequence)
        if route is None:
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
                route, _ = evaluate_sequence(engineer, head)
                if route is not None:
                    break
            if route is None:
                # не помогло даже это: оставляем только начатое
                prefix = [o for o in sequence if o.id in prefix_ids]
                dropped = [o for o in sequence if o.id not in prefix_ids]
                route, _ = evaluate_sequence(engineer, prefix)
                if route is None:
                    route = Route(engineer_id=engineer.id)
            orphans.extend(dropped)
        routes[engineer.id] = route

    # вставка «сирот»: срочные и ранние окна первыми
    orphans.sort(key=lambda o: (0 if o.priority == norms.PRIORITY_URGENT else 1,
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
                if best is None or score < best[0]:
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
        if order.priority == norms.PRIORITY_URGENT:
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


# --- вытеснение обычной заявки срочной ---------------------------------------

REASON_DISPLACED = "displaced_by_urgent"


def _try_insert(engineer: Engineer, route: Route, by_id: dict[str, Order],
                order: Order, first_free: int) -> tuple[float, Route] | None:
    """Лучшая допустимая вставка заявки в маршрут после замороженного префикса."""
    best: tuple[float, Route] | None = None
    for position in range(first_free, len(route.stops) + 1):
        ok, delta, new_route = insertion_cost(engineer, route, by_id, order, position)
        if ok and (best is None or delta < best[0]):
            best = (delta, new_route)
    return best


MAX_DISPLACED = 3          # сколько обычных заявок готовы сдвинуть ради аварии


def _place_urgent_with_displacement(
        order: Order, routes: dict[str, Route], engineers: list[Engineer],
        by_id: dict[str, Order], frozen: dict[str, list[str]],
        now: int) -> tuple[str, list[Order]] | None:
    """Освобождает место под срочную заявку, сдвигая обычные.

    ТЗ: «Срочная заявка имеет более высокий приоритет при перепланировании».
    Если авария не встаёт в маршрут обычной вставкой, мы снимаем из маршрута
    минимальное число ещё не начатых обычных заявок — столько, сколько нужно,
    чтобы авария поместилась, но не больше MAX_DISPLACED. Снятые заявки затем
    пытаемся передать другим исполнителям; те, кому места не нашлось,
    возвращаются диспетчеру с явной причиной.

    Возвращает (engineer_id, список так и не пристроенных заявок) либо None,
    если места не нашлось даже с вытеснением.
    """
    best: tuple[float, str, Route, list[Order]] | None = None

    for engineer in engineers:
        if not engineer.can_do(order):
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
                    # стоимость: прирост пробега плюс плата за каждую сдвинутую
                    # заявку — так вытесняем как можно меньше и как можно дешевле
                    cost = ((new_route.total_km - route.total_km)
                            + 10.0 * len(victims)
                            + sum(v.duration_min for v in victims) / 60.0)
                    if best is None or cost < best[0]:
                        best = (cost, engineer.id, new_route, victims)
                    break

                # снимаем первую обычную заявку, стоящую после места вставки
                removable = next(
                    (i for i in range(position, len(sequence))
                     if sequence[i].priority != norms.PRIORITY_URGENT),
                    None,
                )
                if removable is None or len(victims) >= MAX_DISPLACED:
                    break
                victims.append(sequence.pop(removable))

    if best is None:
        return None

    _, engineer_id, new_route, victims = best
    routes[engineer_id] = new_route

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
        else:
            homeless.append(victim)

    return engineer_id, homeless


def _resequence_with(engineer: Engineer, route: Route, by_id: dict[str, Order],
                     order: Order, first_free: int) -> tuple[float, Route] | None:
    """Пересобирает незамороженный хвост маршрута, чтобы вместить заявку.

    Обычная вставка сохраняет порядок уже назначенных заявок, и этого часто
    не хватает: новая заявка не влезает между двумя соседними визитами, хотя
    весь хвост можно просто переставить по времени окон. Здесь мы делаем ровно
    то, что сделал бы диспетчер вручную, — раскладываем оставшиеся заявки
    по возрастанию окна и пробуем поставить новую в каждую позицию.
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
        delta = new_route.total_km - route.total_km
        if best is None or delta < best[0]:
            best = (delta, new_route)
    return best
