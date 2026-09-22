"""Порядок приоритетов при нехватке людей.

Постановщик задал его трижды: авария, затем подключение, затем ремонт и
дозаказ по остаточному принципу (чат 18.09 13:30, 19.09 ответ 15, 21.09
15:55). На выгрузках организаторов это правило почти не видно - там узкое
место не приоритет, а квалификация и транспорт, - поэтому проверяем его на
дне, собранном под сам выбор: одна бригада, две заявки в одном окне, взять
можно только одну.
"""
from dispatcher.domain import Engineer, Order
from dispatcher.services.planning.optimizer import solve_optimized

OFFICE_LAT, OFFICE_LON = 55.75, 37.62


def _order(order_id: str, priority: str, skill: str, duration: int = 50) -> Order:
    """Заявка в том же месте и в том же окне: выбор идёт только по приоритету."""
    return Order(
        id=order_id,
        lat=OFFICE_LAT + 0.01,
        lon=OFFICE_LON + 0.01,
        address=f"Адрес заявки {order_id}",
        district="Тестовый",
        duration_min=duration,
        window_start=10 * 60,
        window_end=11 * 60,
        priority=priority,
        required_skill=skill,
        required_vehicle=None,
        equipment=[],
        type_bk="",
        type_hd="",
        control_engineer=None,
        geocode_precision="exact",
    )


def _single_crew(skills: list[str]) -> Engineer:
    """Одна бригада со сменой ровно на одну заявку из пары."""
    return Engineer(
        id="Бригада 1",
        name="Бригада 1",
        lat=OFFICE_LAT,
        lon=OFFICE_LON,
        start_address="Офис участка",
        shift_start=10 * 60,
        shift_end=11 * 60,
        skills=skills,
        vehicle="Автомобиль",
        break_min=0,
    )


def _taken(orders: list[Order], crew: Engineer) -> set[str]:
    plan = solve_optimized(orders, [crew], time_limit_sec=10)
    return {stop.order_id for route in plan.routes for stop in route.stops}


def test_emergency_wins_over_connection():
    orders = [_order("ремонт", "Обычная", "Локальные работы"),
              _order("авария", "Срочная", "Аварийные работы", duration=50)]
    crew = _single_crew(["Локальные работы", "Аварийные работы"])

    taken = _taken(orders, crew)

    assert taken == {"авария"}, "авария обязана вытеснить ремонт"


def test_connection_wins_over_repair():
    orders = [_order("ремонт", "Обычная", "Локальные работы"),
              _order("подключение", "Повышенная", "Работы на подключение и дозаказы")]
    crew = _single_crew(["Локальные работы", "Работы на подключение и дозаказы"])

    taken = _taken(orders, crew)

    assert taken == {"подключение"}, "подключение стоит выше ремонта"


def test_volume_beats_priority():
    """Два ремонта дороже одного подключения: объём - первая метрика ТЗ.

    Приоритет разводит равный выбор, а не разрешает менять две заявки на
    одну: иначе доля закрытых заявок падает, а именно её и просят считать.
    """
    orders = [_order("ремонт 1", "Обычная", "Локальные работы", duration=25),
              _order("ремонт 2", "Обычная", "Локальные работы", duration=25),
              _order("подключение", "Повышенная", "Работы на подключение и дозаказы",
                     duration=60)]
    crew = _single_crew(["Локальные работы", "Работы на подключение и дозаказы"])

    taken = _taken(orders, crew)

    assert taken == {"ремонт 1", "ремонт 2"}, "две заявки важнее одной"
