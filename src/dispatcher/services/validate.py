"""Независимая проверка готового плана на соблюдение ограничений ТЗ.

Эксперты спрашивают прямо: «действительно ли обязательные ограничения реально
проверяются алгоритмом?». Этот модуль отвечает на вопрос машинно. Он ничего
не знает о том, как план построен, и перепроверяет результат с нуля:

  Навык   — требуемый навык заявки входит в список навыков исполнителя;
  Ресурс  — если в заявке указан тип транспорта, у исполнителя он такой же;
  Время   — начало работ внутри окна заявки, а весь маршрут внутри смены
            за вычетом перерыва на обед;
  Логика  — времена и пробег в маршруте пересчитываются заново и сверяются
            с тем, что показывает план; каждая заявка встречается ровно один
            раз и ни одна не теряется между маршрутами и отказами.

Используется в автотестах и доступно кнопкой из интерфейса.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from dispatcher.domain import Engineer, Order, Plan, hhmm
from dispatcher.domain.distance import road_km, travel_minutes

TOLERANCE_KM = 0.01
TOLERANCE_MIN = 0


@dataclass
class Violation:
    rule: str            # 'Навык' | 'Ресурс' | 'Время' | 'Логика'
    engineer_id: str
    order_id: str
    text: str

    def to_dict(self) -> dict:
        return {"rule": self.rule, "engineer_id": self.engineer_id,
                "order_id": self.order_id, "text": self.text}


@dataclass
class ValidationReport:
    violations: list[Violation] = field(default_factory=list)
    checked_stops: int = 0
    checked_routes: int = 0

    @property
    def ok(self) -> bool:
        return not self.violations

    def by_rule(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for v in self.violations:
            out[v.rule] = out.get(v.rule, 0) + 1
        return out

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "checked_routes": self.checked_routes,
            "checked_stops": self.checked_stops,
            "violations": [v.to_dict() for v in self.violations],
            "by_rule": self.by_rule(),
        }


def validate(plan: Plan, orders: list[Order], engineers: list[Engineer]) -> ValidationReport:
    report = ValidationReport()
    by_id = {o.id: o for o in orders}
    engineer_by_id = {e.id: e for e in engineers}
    seen: dict[str, str] = {}

    for route in plan.routes:
        if not route.stops:
            continue
        report.checked_routes += 1
        engineer = engineer_by_id.get(route.engineer_id)
        if engineer is None:
            report.violations.append(Violation(
                "Логика", route.engineer_id, "",
                f"В плане есть маршрут исполнителя «{route.engineer_id}», "
                f"которого нет в списке исполнителей."))
            continue

        lat, lon, clock = engineer.lat, engineer.lon, engineer.shift_start

        for stop in route.stops:
            report.checked_stops += 1
            order = by_id.get(stop.order_id)
            if order is None:
                report.violations.append(Violation(
                    "Логика", engineer.id, stop.order_id,
                    "Заявки нет во входных данных."))
                continue

            if stop.order_id in seen:
                report.violations.append(Violation(
                    "Логика", engineer.id, stop.order_id,
                    f"Заявка назначена дважды: «{seen[stop.order_id]}» "
                    f"и «{engineer.id}»."))
            seen[stop.order_id] = engineer.id

            # --- Навык ---
            if order.required_skill not in engineer.skills:
                report.violations.append(Violation(
                    "Навык", engineer.id, order.id,
                    f"Требуется навык «{order.required_skill}», "
                    f"а у исполнителя только: {', '.join(engineer.skills)}."))

            # --- Ресурс ---
            if order.required_vehicle and engineer.vehicle != order.required_vehicle:
                report.violations.append(Violation(
                    "Ресурс", engineer.id, order.id,
                    f"Требуется транспорт «{order.required_vehicle}», "
                    f"а у исполнителя «{engineer.vehicle}»."))

            # --- Время: пересчитываем маршрут заново ---
            km = road_km(lat, lon, order.lat, order.lon)
            travel = travel_minutes(km, engineer.vehicle)
            arrival = clock + travel
            start = max(arrival, order.window_start)
            end = start + order.duration_min

            if start > order.window_end:
                report.violations.append(Violation(
                    "Время", engineer.id, order.id,
                    f"Начало работ {hhmm(start)} выходит за окно "
                    f"{order.window_text}."))
            if end > engineer.work_end:
                report.violations.append(Violation(
                    "Время", engineer.id, order.id,
                    f"Работы заканчиваются в {hhmm(end)}, а работать можно "
                    f"до {hhmm(engineer.work_end)} "
                    f"(смена {engineer.shift_text})."))

            # --- Логика: совпадает ли показанное с пересчитанным ---
            if abs(stop.travel_km - km) > TOLERANCE_KM:
                report.violations.append(Violation(
                    "Логика", engineer.id, order.id,
                    f"Пробег до точки в плане {stop.travel_km:.2f} км, "
                    f"пересчёт даёт {km:.2f} км."))
            if abs(stop.start - start) > TOLERANCE_MIN:
                report.violations.append(Violation(
                    "Логика", engineer.id, order.id,
                    f"Начало работ в плане {hhmm(stop.start)}, "
                    f"пересчёт даёт {hhmm(start)}."))
            if abs(stop.end - end) > TOLERANCE_MIN:
                report.violations.append(Violation(
                    "Логика", engineer.id, order.id,
                    f"Окончание в плане {hhmm(stop.end)}, "
                    f"пересчёт даёт {hhmm(end)}."))

            lat, lon, clock = order.lat, order.lon, end

    # ни одна заявка не имеет права потеряться между маршрутами и отказами
    unassigned_ids = {u.order_id for u in plan.unassigned}
    for order in orders:
        if order.id not in seen and order.id not in unassigned_ids:
            report.violations.append(Violation(
                "Логика", "", order.id,
                "Заявка потерялась: её нет ни в одном маршруте и нет среди "
                "неназначенных."))

    # каждая неназначенная заявка обязана иметь причину и не быть в маршруте
    for unassigned in plan.unassigned:
        if unassigned.order_id in seen:
            report.violations.append(Violation(
                "Логика", seen[unassigned.order_id], unassigned.order_id,
                "Заявка одновременно назначена и помечена как неназначенная."))
        if not unassigned.reason_text.strip():
            report.violations.append(Violation(
                "Логика", "", unassigned.order_id,
                "У неназначенной заявки не указана причина."))

    return report
