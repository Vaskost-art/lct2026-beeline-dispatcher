"""Событие в течение дня: описание, разбор, срочная заявка.

Поддержаны все события из справочника ТЗ: появилась новая заявка (авария,
подключение или ремонт), заявка отменена, исполнитель недоступен,
исполнитель задерживается.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field

from dispatcher.domain import (
    PRIORITY_HIGH,
    PRIORITY_URGENT,
    SKILL_CONNECT,
    SKILL_EMERGENCY,
    SKILL_LOCAL,
    Engineer,
    Order,
    Plan,
    hhmm,
    norms,
)

KIND_URGENT = "urgent_order"
KIND_CANCEL = "cancel_order"
KIND_UNAVAILABLE = "engineer_unavailable"
KIND_DELAYED = "engineer_delayed"

KIND_TITLES = {
    KIND_URGENT: "Появилась новая заявка",
    KIND_CANCEL: "Заявка отменена",
    KIND_UNAVAILABLE: "Инженер стал недоступен",
    KIND_DELAYED: "Бригада задерживается",
}


@dataclass
class ReplanEvent:
    """Событие переплана: тип, время и предмет."""

    kind: str
    at: int                                   # минуты от полуночи
    order_id: str | None = None               # для отмены
    engineer_id: str | None = None            # для недоступности и задержки
    new_order: Order | None = None            # для срочной заявки
    delay_min: int = 0                        # для задержки, минут

    @property
    def title(self) -> str:
        return KIND_TITLES.get(self.kind, self.kind)

    def describe(self) -> str:
        if self.kind == KIND_URGENT and self.new_order:
            o = self.new_order
            kind = ("авария" if o.priority == PRIORITY_URGENT
                    else "заявка на подключение" if o.priority == PRIORITY_HIGH
                    else "заявка")
            # Тип работ повторять незачем, если он и есть «авария».
            work = "" if o.type_hd.strip().lower() == kind else f"{o.type_hd}, "
            return (f"В {hhmm(self.at)} поступила {kind} {o.id}: "
                    f"{work}{o.district}, окно {o.window_text}, "
                    f"{o.duration_min} мин.")
        if self.kind == KIND_CANCEL:
            return f"В {hhmm(self.at)} отменена заявка {self.order_id}."
        if self.kind == KIND_UNAVAILABLE:
            return (f"В {hhmm(self.at)} исполнитель «{self.engineer_id}» "
                    f"выбыл — оставшиеся заявки нужно передать другим.")
        if self.kind == KIND_DELAYED:
            return (f"В {hhmm(self.at)} бригада «{self.engineer_id}» "
                    f"сообщила о задержке на {self.delay_min} мин: весь "
                    f"остаток её маршрута уезжает на это время вперёд.")
        return f"Событие в {hhmm(self.at)}."


@dataclass
class ReplanResult:
    plan: Plan
    diff: dict = field(default_factory=dict)
    narrative: list[str] = field(default_factory=list)
    frozen: dict[str, list[str]] = field(default_factory=dict)
    engineers: list[Engineer] = field(default_factory=list)
    """Состав исполнителей с учётом события: у выбывшего обрезана смена,
    у остальных остаток дня начинается с момента события. Именно против этого
    состава корректно проверять полученный план."""

    orders: list[Order] = field(default_factory=list)
    """Заявки с учётом события: с добавленной новой или без отменённой."""


def apply_event(orders: list[Order], engineers: list[Engineer],
                event: ReplanEvent) -> tuple[list[Order], list[Engineer]]:
    """Возвращает изменённые списки заявок и исполнителей после события."""
    new_orders = list(orders)
    new_engineers = [deepcopy(e) for e in engineers]

    if event.kind == KIND_CANCEL:
        new_orders = [o for o in new_orders if o.id != event.order_id]

    elif event.kind == KIND_URGENT and event.new_order is not None:
        new_orders = new_orders + [event.new_order]

    # Недоступность исполнителя обрабатывается в replan(): там известно,
    # какие работы он уже начал и обязан довести до конца.

    return new_orders, new_engineers


def make_new_order(order_id: str, lat: float, lon: float, address: str,
                   district: str, duration_min: int, window_start: int,
                   window_end: int, required_skill: str,
                   required_vehicle: str | None = None,
                   type_hd: str | None = None) -> Order:
    """Собирает заявку, поступившую днём, с полным набором полей (ТЗ п. 2.4.1).

    Тип работ и приоритет выводятся из требуемого навыка тем же правилом,
    что и для утренней выгрузки: авария срочная, подключение повышенное,
    ремонт обычный. Днём приходят не только аварии (организаторы, 22.09), и
    обычная заявка не получает права двигать чужие визиты.
    """
    type_bk = next((bk for bk, skill in norms.SKILL_BY_TYPE_BK.items()
                    if skill == required_skill), "Глобальная проблема")
    defaults = {
        SKILL_EMERGENCY: "Авария",
        SKILL_LOCAL: "Нет линка",
        SKILL_CONNECT: "Заявка на подключение",
    }
    return Order(
        id=order_id, lat=lat, lon=lon, address=address, district=district,
        duration_min=duration_min, window_start=window_start,
        window_end=window_end, priority=norms.priority_for(type_bk, ""),
        required_skill=required_skill, required_vehicle=required_vehicle,
        type_bk=type_bk, type_hd=type_hd or defaults.get(required_skill, "Авария"),
        geocode_precision="manual",
    )
