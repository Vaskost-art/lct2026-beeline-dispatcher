"""Объяснение плана языком диспетчера (ТЗ п. 2.1 п.7 и п. 7.2).

Главное правило: объяснение не пересказывает код, а перечисляет проверяемые
факты - какие ограничения отсекли других исполнителей и на сколько километров
любой другой вариант был бы хуже. Альтернативы считаются по-настоящему:
заявка пробуется на вставку в маршрут каждого другого исполнителя.
"""
from __future__ import annotations

from dispatcher.domain import Engineer, Order, Plan, hhmm
from dispatcher.domain.text import decimal
from dispatcher.domain.text import plural as _plural
from dispatcher.services.explain.alternatives import _alternatives
from dispatcher.services.explain.summary import _summary

# сколько отвергнутых альтернатив показывать
MAX_ALTERNATIVES = 4


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
                     f"{decimal(stop.travel_km)} км в пути.")
    else:
        prev_order = by_id[route.stops[position - 1].order_id]
        prev_text = (f"Едет от предыдущей заявки {prev_order.id} "
                     f"({prev_order.district}): {decimal(stop.travel_km)} км, "
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

    headline = (f"Заявку {order.id} выполняет «{engineer.name}» - "
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
        ("Адрес", f"{order.address} - {order.district}"),
        ("Приоритет", order.priority),
    ]
    if order.required_vehicle:
        facts.append(("Требуемый транспорт", order.required_vehicle))
    return facts
