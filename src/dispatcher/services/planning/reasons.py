"""Причины, по которым заявка осталась без исполнителя.

Причина читается диспетчером и подсказывает, что делать. Судить о
выполнимости обязан тот же набор проверок, что и планировщик.
"""
from __future__ import annotations

from dispatcher.domain import Engineer, Order, Unassigned
from dispatcher.domain.distance import road_km, travel_minutes

REASON_TEXT = {
    "no_skill": "Ни у одного исполнителя нет требуемого навыка «{skill}».",
    "no_vehicle": "Требуется транспорт «{vehicle}», но исполнителей с таким "
                  "транспортом нет или у них нет нужного навыка.",
    "window_unreachable": "Ни один подходящий исполнитель не успевает доехать "
                          "во временное окно {window}: смена заканчивается раньше "
                          "или дорога занимает больше времени, чем есть до конца окна.",
    "shift_overflow": "Работа длительностью {duration} мин не помещается в смену "
                      "ни у одного подходящего исполнителя.",
    "no_capacity": "Все подходящие исполнители в окне {window} уже заняты "
                   "другими заявками.",
}


def _reason(code: str, order: Order) -> Unassigned:
    text = REASON_TEXT[code].format(
        skill=order.required_skill,
        vehicle=order.required_vehicle or "—",
        window=order.window_text,
        duration=order.duration_min,
    )
    return Unassigned(order_id=order.id, reason=code, reason_text=text)


def diagnose(order: Order, engineers: list[Engineer]) -> Unassigned:
    """Определяет, почему заявку не удалось назначить.

    Проверки идут от самых жёстких ограничений к самым мягким, поэтому
    диспетчер получает первопричину, а не следствие.
    """
    by_skill = [e for e in engineers if order.required_skill in e.skills]
    if not by_skill:
        return _reason("no_skill", order)

    by_resource = [e for e in by_skill
                   if not order.required_vehicle or e.vehicle == order.required_vehicle]
    if not by_resource:
        return _reason("no_vehicle", order)

    # существует ли исполнитель, который вообще способен выполнить заявку,
    # если бы ехал к ней прямо с базы и был свободен весь день
    reachable = False
    fits_shift = False
    for e in by_resource:
        km = road_km(e.lat, e.lon, order.lat, order.lon)
        arrival = e.shift_start + travel_minutes(km, e.vehicle)
        start = max(arrival, order.window_start)
        if start <= order.window_end:
            reachable = True
            # work_end: заявка, не влезающая именно из-за обеда, иначе
            # получит причину «все исполнители заняты» при пустом маршруте
            if start + order.duration_min <= e.work_end:
                fits_shift = True
                break

    if not reachable:
        return _reason("window_unreachable", order)
    if not fits_shift:
        return _reason("shift_overflow", order)
    return _reason("no_capacity", order)
