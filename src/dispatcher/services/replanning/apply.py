"""Перестроение дня после события."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from dispatcher.domain import PRIORITY_URGENT, Engineer, Order, Plan, Unassigned, hhmm
from dispatcher.services.planning.costs import DEFAULT_TIME_LIMIT_SEC
from dispatcher.services.planning.optimizer import solve_optimized
from dispatcher.services.replanning.diff import build_diff, describe_diff
from dispatcher.services.replanning.events import (
    KIND_DELAYED,
    KIND_UNAVAILABLE,
    ReplanEvent,
    ReplanResult,
    apply_event,
)
from dispatcher.services.replanning.freeze import _frozen_prefixes
from dispatcher.services.replanning.repair import MODE_FULL, MODE_MINIMAL, MODE_TITLES, _repair


def replan(orders: list[Order], engineers: list[Engineer], current: Plan,
           event: ReplanEvent, mode: str = "minimal",
           time_limit_sec: int = DEFAULT_TIME_LIMIT_SEC,
           issued: dict[str, dict[str, int]] | None = None) -> ReplanResult:
    """Строит новый план на остаток дня и объясняет, что изменилось.

    mode='minimal' — точечно встроить изменение, не трогая остальные назначения;
    mode='full'    — перепланировать весь остаток дня заново.

    `issued` — что бригады получили в офисе утром: днём заявку берёт только
    та, у кого нужное оборудование с собой.
    """
    now = event.at
    new_orders, new_engineers = apply_event(orders, engineers, event)

    frozen = _frozen_prefixes(current, now)
    # Событие могло убрать заявку из дня (отмена). Оставить её в префиксе
    # значит сдвинуть границу «уже начатого» и заморозить следующий визит,
    # к которому бригада ещё не подъезжала.
    alive = {o.id for o in new_orders}
    frozen = {eid: [oid for oid in ids if oid in alive]
              for eid, ids in frozen.items()}
    frozen = {eid: ids for eid, ids in frozen.items() if ids}
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
                # Обед из укороченного дня не вычитается: он либо уже был
                # внутри отработанного куска, либо не состоится вовсе.
                # Вычесть его здесь значит отнять у бригады время, которое
                # она реально отработала, и начатая работа перестанет
                # помещаться в собственную смену.
                engineer.break_min = 0
        if event.engineer_id:
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
        prefix = frozen.get(event.engineer_id or "") or []
        if prefix:
            last_id = prefix[-1]
            route = next((r for r in current.routes
                          if r.engineer_id == event.engineer_id), None)
            last_stop = next((s for s in (route.stops if route else [])
                              if s.order_id == last_id), None)
            # Бригада освободится через delay минут после того, как закончит
            # текущую работу, а если она уже закончена — через delay минут от
            # момента звонка. Держать её можно только длительностью последнего
            # начатого визита: это единственный рычаг, поэтому у такого визита
            # в плане показано время окончания, когда бригада снова свободна.
            if last_stop is not None:
                free_at = max(last_stop.end, now) + delay
                extra = max(0, free_at - last_stop.end)
            else:
                extra = delay
            new_orders = [replace(o, duration_min=o.duration_min + extra)
                          if o.id == last_id else o for o in new_orders]
        else:
            for engineer in new_engineers:
                if engineer.id == event.engineer_id:
                    # Отсчёт от начала смены, если бригада ещё не выехала:
                    # «выедем на час позже» в 06:00 при смене с 09:00 должно
                    # давать 10:00, а не оставлять смену нетронутой.
                    engineer.shift_start = min(
                        max(engineer.shift_start, now) + delay,
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

    # Работа, к которой бригада уже приступила, обязана помещаться в её
    # рабочее время. Иначе замороженный префикс не проходит пересчёт, и весь
    # день бригады пропадает из плана, а закрытые утром заявки всплывают
    # среди неназначенных.
    frozen_end: dict[str, int] = {}
    plannable_by_id = {o.id: o for o in new_orders}
    for route in current.routes:
        ids = frozen.get(route.engineer_id) or []
        for stop in route.stops:
            if stop.order_id not in ids:
                continue
            planned = plannable_by_id.get(stop.order_id)
            # длительность могла вырасти: задержка записывается в неё
            end = stop.start + (planned.duration_min if planned else
                                stop.end - stop.start)
            frozen_end[route.engineer_id] = max(
                frozen_end.get(route.engineer_id, 0), end)

    # Исполнители, у которых ничего не заморожено, начинают остаток дня «сейчас».
    adjusted: list[Engineer] = []
    for engineer in new_engineers:
        e = deepcopy(engineer)
        if not frozen.get(e.id):
            e.shift_start = max(e.shift_start, min(now, e.shift_end))
        need = frozen_end.get(e.id)
        if need is not None and e.work_end < need:
            # Ровно столько, чтобы начатое поместилось: свободного места
            # после него не появляется.
            e.shift_end = need + e.break_min
        adjusted.append(e)

    if mode == MODE_MINIMAL:
        new_plan = _repair(plannable, adjusted, current, event, now, frozen,
                           issued)
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
             if o.priority == PRIORITY_URGENT and o.id not in assigned_ids]
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
