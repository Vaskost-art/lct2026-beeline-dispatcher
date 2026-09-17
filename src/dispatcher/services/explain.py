"""Объяснение плана языком диспетчера (ТЗ п. 2.1 п.7 и п. 7.2).

Главное правило: объяснение не пересказывает код, а перечисляет проверяемые
факты — какие ограничения отсекли других исполнителей и на сколько километров
любой другой вариант был бы хуже. Альтернативы считаются по-настоящему:
заявка пробуется на вставку в маршрут каждого другого исполнителя.
"""
from __future__ import annotations

from dispatcher.domain import Engineer, Order, Plan, hhmm
from dispatcher.domain.distance import road_km, travel_minutes
from dispatcher.services.routing import insertion_cost

# сколько отвергнутых альтернатив показывать
MAX_ALTERNATIVES = 4


def _plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def explain_assignment(order: Order, plan: Plan, orders: list[Order],
                       engineers: list[Engineer]) -> dict:
    """Почему заявка назначена именно этому исполнителю."""
    by_id = {o.id: o for o in orders}
    engineer_by_id = {e.id: e for e in engineers}

    found = plan.stop_of(order.id)
    if found is None:
        unassigned = next((u for u in plan.unassigned if u.order_id == order.id), None)
        return {
            "order_id": order.id,
            "assigned": False,
            "headline": "Заявка не назначена",
            "reason": unassigned.reason_text if unassigned else "Причина не определена",
            "facts": _order_facts(order),
            "alternatives": _alternatives(
                order, plan, by_id, engineers, exclude=None)[:MAX_ALTERNATIVES + 4],
        }

    engineer_id, position, stop = found
    engineer = engineer_by_id[engineer_id]
    route = next(r for r in plan.routes if r.engineer_id == engineer_id)

    facts = _order_facts(order)
    facts.append(("Исполнитель", f"{engineer.name}, смена {engineer.shift_text}, "
                                 f"транспорт: {engineer.vehicle}"))
    facts.append(("Навыки исполнителя", ", ".join(engineer.skills)))

    # чем обосновано место в маршруте
    if position == 0:
        prev_text = (f"Первая заявка в маршруте: выезд с базы в "
                     f"{hhmm(stop.arrival - stop.travel_min)}, "
                     f"{stop.travel_km:.1f} км в пути.")
    else:
        prev_order = by_id[route.stops[position - 1].order_id]
        prev_text = (f"Едет от предыдущей заявки {prev_order.id} "
                     f"({prev_order.district}): {stop.travel_km:.1f} км, "
                     f"{stop.travel_min} мин.")

    timing = (f"Приезжает в {hhmm(stop.arrival)}, работает "
              f"{hhmm(stop.start)}–{hhmm(stop.end)}.")
    if stop.wait_min > 0:
        timing += (f" Ждёт открытия окна {stop.wait_min} "
                   f"{_plural(stop.wait_min, 'минуту', 'минуты', 'минут')}.")

    alternatives = _alternatives(order, plan, by_id, engineers, exclude=engineer_id)
    cheaper = [a for a in alternatives if a.get("extra_km") is not None
               and a["extra_km"] < 0]
    shown = alternatives[:MAX_ALTERNATIVES + 4]

    headline = (f"Заявку {order.id} выполняет «{engineer.name}» — "
                f"{position + 1}-й визит в маршруте")

    return {
        "order_id": order.id,
        "assigned": True,
        "engineer_id": engineer_id,
        "position": position + 1,
        "headline": headline,
        "facts": facts,
        "route_reason": prev_text,
        "timing_reason": timing,
        "alternatives": shown,
        "alternatives_total": len(alternatives),
        "summary": _summary(order, engineer, stop, position, alternatives, cheaper),
    }


def _order_facts(order: Order) -> list[tuple[str, str]]:
    facts = [
        ("Тип работ", f"{order.type_hd} ({order.type_bk})"),
        ("Требуемый навык", order.required_skill),
        ("Временное окно", order.window_text),
        ("Длительность", f"{order.duration_min} мин"),
        ("Адрес", f"{order.address} — {order.district}"),
        ("Приоритет", order.priority),
    ]
    if order.required_vehicle:
        facts.append(("Требуемый транспорт", order.required_vehicle))
    return facts


def _alternatives(order: Order, plan: Plan, by_id: dict[str, Order],
                  engineers: list[Engineer], exclude: str | None) -> list[dict]:
    """Проверяет каждого другого исполнителя и объясняет, почему не он.

    Для тех, кто проходит по навыку и транспорту, заявка реально пробуется
    на вставку в текущий маршрут — так получается честная цифра «был бы
    длиннее на N км», а не общие слова.
    """
    route_by_id = {r.engineer_id: r for r in plan.routes}
    result: list[dict] = []
    current_km = None
    if exclude is not None:
        found = plan.stop_of(order.id)
        if found:
            current_km = found[2].travel_km

    for engineer in engineers:
        if engineer.id == exclude:
            continue

        if order.required_skill not in engineer.skills:
            result.append({
                "engineer_id": engineer.id, "possible": False,
                "reason": f"нет навыка «{order.required_skill}»",
                "blocked_by": "Навык",
            })
            continue

        if order.required_vehicle and engineer.vehicle != order.required_vehicle:
            result.append({
                "engineer_id": engineer.id, "possible": False,
                "reason": f"транспорт «{engineer.vehicle}», "
                          f"а заявке нужен «{order.required_vehicle}»",
                "blocked_by": "Ресурс",
            })
            continue

        route = route_by_id.get(engineer.id)
        if route is None:
            continue

        best_delta = None
        for position in range(len(route.stops) + 1):
            ok, delta, _ = insertion_cost(engineer, route, by_id, order, position)
            if ok and (best_delta is None or delta < best_delta):
                best_delta = delta

        if best_delta is None:
            km = road_km(engineer.lat, engineer.lon, order.lat, order.lon)
            travel = travel_minutes(km, engineer.vehicle)
            arrival = engineer.shift_start + travel
            # Причина называется по тому, что действительно отсекло. Сказать
            # «маршрут занят» бригаде с пустым маршрутом значит отправить
            # диспетчера разгружать того, кто и так простаивает.
            if arrival > order.window_end:
                why = (f"не успевает в окно {order.window_text}: "
                       f"даже с базы дорога занимает {travel} мин")
            elif max(arrival, order.window_start) + order.duration_min > engineer.work_end:
                why = (f"работа на {order.duration_min} мин не помещается "
                       f"в смену ({engineer.shift_text}) даже первой в маршруте")
            elif not route.stops:
                why = (f"не может взять заявку даже с пустым маршрутом: "
                       f"окно {order.window_text} не сходится со сменой "
                       f"({engineer.shift_text})")
            else:
                why = (f"маршрут уже занят — заявка не встаёт ни в одну позицию "
                       f"без нарушения окон или конца смены "
                       f"({engineer.shift_text})")
            result.append({
                "engineer_id": engineer.id, "possible": False,
                "reason": why, "blocked_by": "Время",
            })
            continue

        entry = {
            "engineer_id": engineer.id, "possible": True,
            "extra_km": round(best_delta, 2),
            "blocked_by": None,
            "reason": f"мог бы взять, но маршрут вырос бы на {best_delta:.1f} км",
        }
        if current_km is not None:
            entry["vs_current_km"] = round(best_delta - current_km, 2)
        result.append(entry)

    # сначала возможные (по возрастанию удорожания), затем отсечённые.
    # Возвращаем полный список: счётчики в объяснении должны считаться по нему,
    # усечение для показа делает вызывающая сторона.
    result.sort(key=lambda a: (not a["possible"],
                              a.get("extra_km", 0.0) if a["possible"] else 0.0))
    return result


def _summary(order: Order, engineer: Engineer, stop, position: int,
             alternatives: list[dict], cheaper: list[dict]) -> str:
    """Одно-два предложения, которые диспетчер читает первыми."""
    blocked = [a for a in alternatives if not a["possible"]]
    by_skill = sum(1 for a in blocked if a["blocked_by"] == "Навык")
    by_vehicle = sum(1 for a in blocked if a["blocked_by"] == "Ресурс")
    by_time = sum(1 for a in blocked if a["blocked_by"] == "Время")

    parts = [
        f"Выбран исполнитель «{engineer.name}»: есть навык "
        f"«{order.required_skill}»"
    ]
    if order.required_vehicle:
        parts.append(f" и требуемый транспорт «{order.required_vehicle}»")
    parts.append(
        f", начало работ в {hhmm(stop.start)} попадает в окно "
        f"{order.window_text}, работа укладывается в смену {engineer.shift_text}"
    )
    head = "".join(parts) + "."

    cut = []
    if by_skill:
        cut.append(f"{by_skill} без нужного навыка")
    if by_vehicle:
        cut.append(f"{by_vehicle} с неподходящим транспортом")
    if by_time:
        cut.append(f"{by_time} "
                   f"{_plural(by_time, 'не успевал', 'не успевали', 'не успевали')} "
                   f"по времени")
    tail = ""
    if cut:
        tail = f" Остальные исполнители не подошли: {', '.join(cut)}."

    best_alt = next((a for a in alternatives if a["possible"]), None)
    if best_alt:
        tail += (f" Ближайшая альтернатива — {best_alt['engineer_id']}: "
                 f"его маршрут вырос бы на {best_alt['extra_km']:.1f} км.")
    return head + tail


def explain_route(engineer: Engineer, plan: Plan,
                  orders: list[Order]) -> dict:
    """Краткая сводка по маршруту одного исполнителя."""
    by_id = {o.id: o for o in orders}
    route = next((r for r in plan.routes if r.engineer_id == engineer.id), None)
    if route is None or not route.stops:
        return {
            "engineer_id": engineer.id,
            "used": False,
            "summary": f"«{engineer.name}» — без заявок: план закрывается "
                       f"меньшим числом людей.",
            "steps": [],
        }

    steps = []
    for i, stop in enumerate(route.stops):
        order = by_id[stop.order_id]
        steps.append({
            "n": i + 1,
            "order_id": order.id,
            "district": order.district,
            "address": order.address,
            "type": order.type_hd,
            "arrival": hhmm(stop.arrival),
            "start": hhmm(stop.start),
            "end": hhmm(stop.end),
            "travel_km": round(stop.travel_km, 2),
            "travel_min": stop.travel_min,
            "wait_min": stop.wait_min,
            "priority": order.priority,
            "text": (f"{hhmm(stop.start)}–{hhmm(stop.end)} · {order.district}, "
                     f"{order.address} · {order.type_hd} "
                     f"({order.duration_min} мин, {stop.travel_km:.1f} км в пути)"),
        })

    districts = sorted({by_id[s.order_id].district for s in route.stops})
    summary = (
        f"{engineer.vehicle}, смена {engineer.shift_text}. "
        f"В пути {route.total_travel_min} мин, на работах "
        f"{route.total_work_min} мин. "
        f"Районы: {', '.join(districts[:3])}"
        f"{' и другие' if len(districts) > 3 else ''}."
    )
    return {
        "engineer_id": engineer.id,
        "used": True,
        "summary": summary,
        "steps": steps,
    }


def explain_plan(plan: Plan, orders: list[Order], engineers: list[Engineer],
                 metrics: dict) -> dict:
    """Общее объяснение: что за план и за счёт чего он такой."""
    used = metrics["used_engineers"]
    available = metrics["engineers_available"]
    assigned = metrics["orders_assigned"]
    total = metrics["orders_total"]

    lines = [
        f"План закрывает {assigned} из {total} "
        f"{_plural(total, 'заявки', 'заявок', 'заявок')} силами {used} "
        f"{_plural(used, 'исполнителя', 'исполнителей', 'исполнителей')} "
        f"из {available} доступных.",
        f"Суммарный пробег — {metrics['total_km']:.1f} км, "
        f"в среднем {metrics['avg_km_per_order']:.1f} км на заявку. "
        f"Время в пути составляет {metrics['travel_share'] * 100:.0f}% "
        f"от общего времени работы бригад.",
    ]
    if plan.unassigned:
        by_reason: dict[str, int] = {}
        for u in plan.unassigned:
            by_reason[u.reason_text] = by_reason.get(u.reason_text, 0) + 1
        top = sorted(by_reason.items(), key=lambda kv: -kv[1])[:3]
        lines.append(
            "Не удалось назначить "
            f"{len(plan.unassigned)} "
            f"{_plural(len(plan.unassigned), 'заявку', 'заявки', 'заявок')}. "
            "Основные причины: " + " ".join(f"{text} (×{n})" for text, n in top)
        )
    else:
        lines.append("Все заявки распределены.")

    return {"lines": lines, "text": " ".join(lines)}
