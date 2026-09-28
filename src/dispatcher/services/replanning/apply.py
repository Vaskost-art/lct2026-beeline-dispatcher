"""Перестроение дня после события."""
from __future__ import annotations

from dataclasses import replace

from dispatcher.domain import Engineer, Order, Plan, Unassigned, hhmm
from dispatcher.services.planning.costs import DEFAULT_TIME_LIMIT_SEC
from dispatcher.services.replanning.diff import build_diff, describe_diff
from dispatcher.services.replanning.emergency import (
    describe_reaction,
    reaction,
    stuck_emergencies,
)
from dispatcher.services.replanning.events import (
    KIND_DELAYED,
    KIND_UNAVAILABLE,
    ReplanEvent,
    ReplanResult,
    apply_event,
)
from dispatcher.services.replanning.freeze import (
    _frozen_prefixes,
    merge_frozen,
    shifts_after_event,
)
from dispatcher.services.replanning.newcomer import newcomer_outcome, ordinary_newcomer
from dispatcher.services.replanning.rebuild import lost_by_rebuild, rebuild_rest
from dispatcher.services.replanning.repair import MODE_MINIMAL, MODE_TITLES, _repair
from dispatcher.services.roster import add_home_crews, working_crews
from dispatcher.services.statuses import frozen_by_status
from dispatcher.services.statuses import plannable as plannable_by_status


def replan(orders: list[Order], engineers: list[Engineer], current: Plan,
           event: ReplanEvent, mode: str = "minimal",
           time_limit_sec: int = DEFAULT_TIME_LIMIT_SEC,
           issued: dict[str, dict[str, int]] | None = None,
           statuses: dict[str, str] | None = None,
           locked: dict[str, str] | None = None,
           on_shift: list[str] | None = None) -> ReplanResult:
    """Строит новый план на остаток дня и объясняет, что изменилось.

    mode='minimal' - точечно встроить изменение, не трогая остальные назначения;
    mode='full'    - перепланировать весь остаток дня заново.

    `issued` - что бригады получили в офисе утром: днём заявку берёт только
    та, у кого нужное оборудование с собой. `locked` - заявки, которые
    диспетчер закрепил за бригадой: они остаются у неё в обоих режимах.
    `on_shift` - кто вышел на смену: остальных событие из дома не вызывает.

    `statuses` - что диспетчер отметил со слов бригад: отменённая заявка
    уходит из дня, а начатая и завершённая остаются на своих местах, даже
    если по расписанию бригада к ним ещё не подъезжала. Факт важнее
    расписания: расписание - это прогноз, а отметка - то, что уже случилось.
    """
    now = event.at
    marks = statuses or {}
    # Пересобрать остаток дня можно ради аварии, но не ради обычной заявки:
    # она не должна перестраивать сформированный план (организаторы, 22.09).
    if ordinary_newcomer(event) is not None:
        mode = MODE_MINIMAL
    new_orders, new_engineers = apply_event(orders, engineers, event)
    # Отменённая заявка остаётся в дне, но в расчёт не идёт: выброшенная из
    # дня, она теряла отметку в счётчике, а её номер снова выдавался новой
    # аварии, и та исчезала бесследно.
    cancelled = [o for o in new_orders if o not in plannable_by_status(new_orders, marks)]
    new_orders = plannable_by_status(new_orders, marks)

    frozen = merge_frozen(_frozen_prefixes(current, now),
                           frozen_by_status(current, marks))
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
        # Бригада не выбывает - она сдвигается во времени.
        #
        # Если работы уже начаты, двигать начало смены нельзя: начатый визит
        # стоит раньше и модель станет противоречивой. Поэтому задержку
        # записываем в последний начатый визит - он длится на delay_min
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
            # текущую работу, а если она уже закончена - через delay минут от
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

    # Незапущенные заявки с закрывшимся окном - явной причиной.
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

    adjusted = shifts_after_event(current, new_orders, new_engineers, frozen, now)
    working = working_crews(adjusted, on_shift, frozen)

    if mode == MODE_MINIMAL:
        new_plan = _repair(plannable, working, current, event, now, frozen,
                           issued, locked)
    else:
        new_plan, frozen = rebuild_rest(current, plannable, working, event, now,
                                        frozen, time_limit_sec, issued, locked)
    # Запасной расчёт без заморозки переставляет и начатое: список
    # изменений не должен называть такие заявки нетронутыми.
    frozen_ids = {oid for ids in frozen.values() for oid in ids}

    new_plan.unassigned = [u for u in new_plan.unassigned
                           if u.order_id not in {e.order_id for e in expired}]
    add_home_crews(new_plan, adjusted, plannable, working)
    new_plan.unassigned.extend(expired)
    new_plan.strategy = "replanned"

    diff = build_diff(current, new_plan, orders, new_orders, frozen_ids, event)
    diff["mode"] = mode
    diff["mode_title"] = MODE_TITLES.get(mode, mode)

    narrative = describe_diff(diff, event)
    arrival = reaction(new_plan, event)
    if arrival is not None:
        diff["reaction"] = arrival
        narrative.append(describe_reaction(arrival))
    outcome = newcomer_outcome(new_plan, event)
    if outcome is not None:
        diff["new_order"] = outcome

    if mode == MODE_MINIMAL:
        narrative.extend(stuck_emergencies(new_plan, new_orders))
    elif lost := lost_by_rebuild(current, new_plan, plannable):
        diff["lost"] = lost
        narrative.append(f"Пересборка сняла заявки, которые были в плане: {', '.join(lost)}. "
                         f"Точечная правка может их сохранить.")

    return ReplanResult(plan=new_plan, diff=diff, narrative=narrative,
                        frozen=frozen, engineers=adjusted, orders=new_orders + cancelled)
