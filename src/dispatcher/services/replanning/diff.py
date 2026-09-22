"""Чем новый план отличается от прежнего, языком диспетчера."""
from __future__ import annotations

from typing import TypedDict

from dispatcher.domain import Order, Plan, hhmm
from dispatcher.services.replanning.events import ReplanEvent


class EngineerDiff(TypedDict):
    """Как изменился день одного исполнителя."""

    engineer_id: str
    orders_before: int
    orders_after: int
    km_before: float
    km_after: float
    orders_delta: int
    km_delta: float


#: Сдвиг визита меньше этого клиенту не заметен и звонка не требует, минут.
RETIME_TOLERANCE_MIN = 5


def _ranks(plan: Plan, keep: set[str]) -> dict[str, int]:
    """Порядковый номер визита среди заявок из `keep` в его маршруте."""
    out: dict[str, int] = {}
    for route in plan.routes:
        kept = [stop.order_id for stop in route.stops if stop.order_id in keep]
        out.update({order_id: rank for rank, order_id in enumerate(kept)})
    return out


def _starts(plan: Plan) -> dict[str, int]:
    return {stop.order_id: stop.start for route in plan.routes for stop in route.stops}


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
    # Порядок сравнивается только среди заявок, оставшихся у той же бригады:
    # вставка новой заявки сдвигает номера всех следующих визитов, и раньше
    # они значились как «сменила место», хотя ни порядок, ни время у них не
    # менялись.
    same_crew = {oid for oid, (crew, _) in pos_before.items()
                 if pos_after.get(oid, ("", 0))[0] == crew}
    rank_before, rank_after = _ranks(before, same_crew), _ranks(after, same_crew)
    start_before, start_after = _starts(before), _starts(after)
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
        elif rank_before.get(order_id) != rank_after.get(order_id):
            status = "resequenced"
        elif abs(start_after[order_id] - start_before[order_id]) > RETIME_TOLERANCE_MIN:
            status = "retimed"
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
            # На сколько минут сдвинулся визит: по нему служба поддержки
            # предупреждает клиента, которому уже назвали время.
            "shift_min": (start_after[order_id] - start_before[order_id]
                          if a and b else None),
        })

    km_before = {r.engineer_id: r.total_km for r in before.routes}
    km_after = {r.engineer_id: r.total_km for r in after.routes}
    n_before = {r.engineer_id: len(r.stops) for r in before.routes}
    n_after = {r.engineer_id: len(r.stops) for r in after.routes}

    engineer_rows = []
    for engineer_id in sorted(set(km_before) | set(km_after)):
        was, now = n_before.get(engineer_id, 0), n_after.get(engineer_id, 0)
        km_was = round(km_before.get(engineer_id, 0.0), 2)
        km_now = round(km_after.get(engineer_id, 0.0), 2)
        row: EngineerDiff = {
            "engineer_id": engineer_id,
            "orders_before": was,
            "orders_after": now,
            "km_before": km_was,
            "km_after": km_now,
            "orders_delta": now - was,
            "km_delta": round(km_now - km_was, 2),
        }
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
    "retimed": "визит сдвинут по времени",
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
    for key in ("added", "cancelled", "moved", "resequenced", "retimed", "rescued",
                "dropped"):
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
