"""Кто ещё мог взять заявку и во что это обошлось бы.

Альтернативы считаются по-настоящему: заявка пробуется на вставку в
маршрут каждого другого исполнителя, а не оцениваются на глаз.
"""
from __future__ import annotations

from dispatcher.domain import Engineer, Order, Plan
from dispatcher.domain.distance import road_km, travel_minutes
from dispatcher.domain.text import decimal
from dispatcher.services.routing import insertion_cost

MAX_ALTERNATIVES = 4


def _alternatives(order: Order, plan: Plan, by_id: dict[str, Order],
                  engineers: list[Engineer], exclude: str | None) -> list[dict]:
    """Проверяет каждого другого исполнителя и объясняет, почему не он.

    Для тех, кто проходит по навыку и транспорту, заявка реально пробуется
    на вставку в текущий маршрут - так получается честная цифра «был бы
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
                why = (f"маршрут уже занят - заявка не встаёт ни в одну позицию "
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
            "reason": f"мог бы взять, но маршрут вырос бы на {decimal(best_delta)} км",
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
