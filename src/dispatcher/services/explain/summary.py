"""Краткая формулировка, почему заявка досталась этому исполнителю."""
from __future__ import annotations

from dispatcher.domain import Engineer, Order, hhmm
from dispatcher.domain.text import plural as _plural


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
