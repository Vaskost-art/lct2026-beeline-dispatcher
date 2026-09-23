"""Сколько бригад не хватает, чтобы разошлись заявки плана на экране.

Постановщик: число исполнителей заранее не задано, их можно добавлять, а
правильный ответ сервиса на непомещающиеся заявки - «нужно ещё N
исполнителей».

Считается от плана, который видит диспетчер, а не от своего расчёта: раньше
нехватка бралась по быстрому расчёту с нуля, и на Востоке экран одновременно
показывал 66 из 66 заявок и «нужно ещё 2 бригады».
"""
from __future__ import annotations

from collections.abc import Callable

from dispatcher.domain import Engineer, Order, Plan, shifts
from dispatcher.domain.catalog import VEHICLE_CAR
from dispatcher.domain.crew_profiles import skills_for_index, vehicle_for_index
from dispatcher.domain.text import plural
from dispatcher.services.planning.crew_sizing import day_bounds

#: Как зовут планировщик: заявки и бригады на входе, план на выходе.
type Solver = Callable[[list[Order], list[Engineer]], Plan]

#: Сколько бригад подряд можно добавить без единой новой заявки, прежде чем
#: признать, что дело не в людях.
FRUITLESS_LIMIT = 2

#: Дальше этого числа бригад подбор не идёт: участок такого размера означает
#: ошибку в данных, а не нехватку людей.
MAX_EXTRA_CREWS = 20


def _next_crew(number: int, pending: list[Order], orders: list[Order],
               office_lat: float, office_lon: float, office_address: str) -> Engineer:
    """Бригада под самую частую потребность среди нераспределённых заявок."""
    start, end = day_bounds(orders)
    skills = sorted({o.required_skill for o in pending})[:3] or None
    needs_car = any(o.required_vehicle for o in pending)
    return Engineer(
        id=f"Новая бригада {number}", name=f"Новая бригада {number}",
        lat=office_lat, lon=office_lon,
        start_address=office_address or "Офис участка",
        shift_start=start, shift_end=end,
        skills=skills or skills_for_index(number, number + 1),
        vehicle=VEHICLE_CAR if needs_car else vehicle_for_index(number, number + 1, 0),
        break_min=shifts.break_minutes(start, end),
    )


def crews_shortfall(plan: Plan, orders: list[Order], solve: Solver,
                    office_lat: float, office_lon: float,
                    office_address: str) -> dict[str, object]:
    """Сколько ещё бригад и каких нужно для заявок, оставшихся без исполнителя.

    Сложившиеся маршруты не пересчитываются: новые бригады подбираются
    только под заявки, которых нет в плане. Бригады добавляются по одной,
    пока каждая новая забирает хотя бы одну заявку. Если две подряд не
    забрали ничего, причина не в числе людей, и об этом говорится прямо.
    """
    left_ids = {u.order_id for u in plan.unassigned}
    left = [o for o in orders if o.id in left_ids]
    if not left:
        # Форма ответа одна на обе ветки: экран не должен гадать, есть ли
        # ключ, и подставлять за сервис значение по умолчанию.
        return {"missing": 0, "assigned": plan.assigned_count,
                "still_unassigned": 0, "profiles": [],
                "reason": "", "limited_by_people": False}

    extra: list[Engineer] = []
    added: list[Engineer] = []
    best, fruitless, pending = 0, 0, left
    while len(extra) < MAX_EXTRA_CREWS and fruitless < FRUITLESS_LIMIT and pending:
        extra.append(_next_crew(len(extra) + 1, pending, orders,
                                office_lat, office_lon, office_address))
        attempt = solve(left, extra)
        if attempt.assigned_count > best:
            best, fruitless, added = attempt.assigned_count, 0, list(extra)
        else:
            fruitless += 1
        placed = {s.order_id for r in attempt.routes for s in r.stops}
        pending = [o for o in left if o.id not in placed]

    still_left = len(left) - best
    # Чего именно не хватает. «Нужно ещё 2 бригады» не отвечает на вопрос
    # диспетчера: людей каких - с машиной, с каким навыком, на какие часы.
    return {
        "missing": len(added),
        "profiles": [{"vehicle": crew.vehicle, "skills": list(crew.skills),
                      "shift": crew.shift_text} for crew in added],
        "assigned": plan.assigned_count + best,
        "still_unassigned": still_left,
        # Заявки, которые не берёт даже свободная бригада, упираются не в
        # число людей: иначе диспетчер будет искать людей там, где мешает окно.
        "reason": (f"Ещё {still_left} "
                   f"{plural(still_left, 'заявку', 'заявки', 'заявок')} "
                   "не берёт ни одна бригада: мешает временное окно или "
                   "требования заявки, а не число людей."
                   if still_left else ""),
        "limited_by_people": bool(added),
    }
