"""Решатель и построитель маршрута обязаны считать дорогу одинаково.

Расхождение в одну минуту выбрасывает целый маршрут, и ни одной ошибки в
журнале при этом не появляется: обе стороны считают себя правыми. Поэтому
собственных формул расстояния и времени нет ни у кого, кроме общего модуля.
"""
import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "dispatcher"


def test_router_has_no_formula_of_its_own(scenarios):
    """Построитель маршрута берёт дорогу из общих функций, а не считает сам."""
    from dispatcher.domain.distance import road_km, travel_minutes
    from dispatcher.services.routing import build_leg

    checked = 0
    for scenario in scenarios.values():
        for engineer in scenario.engineers:
            for order in scenario.orders:
                leg = build_leg(engineer, engineer.lat, engineer.lon,
                                engineer.shift_start, order)
                if not leg.feasible:
                    continue
                km = road_km(engineer.lat, engineer.lon, order.lat, order.lon)
                assert leg.stop is not None
                assert leg.stop.travel_min == travel_minutes(km, engineer.vehicle)
                assert abs(leg.stop.travel_km - km) < 1e-9
                checked += 1
    # Без счётчика тест зелёный и на выборке, где ни один визит не выполним.
    assert checked > 100


def test_only_one_module_defines_the_distance():
    """Формулы расстояния и скорости живут в одном модуле домена.

    Проверка идёт по исходникам: числа, которыми считают километры и минуты,
    не имеют права появиться во втором месте, даже совпадающие.
    """
    formulas = re.compile(r"6371|111\.19|DETOUR_FACTOR\s*=|\w+_KMH\s*=")
    guilty = [
        path.relative_to(SRC).as_posix()
        for path in SRC.rglob("*.py")
        if formulas.search(path.read_text(encoding="utf-8"))
    ]
    assert sorted(guilty) == ["domain/distance.py", "domain/norms.py",
                              "domain/travel.py"], guilty


def test_solver_asks_the_domain_for_every_kilometre():
    """В оптимизаторе нет своей арифметики расстояния.

    Время в пути для решателя считается заранее матрицей в `transit.py`,
    поэтому решатель проверяется вместе с ней.
    """
    planning = SRC / "services" / "planning"
    source = "".join((planning / name).read_text(encoding="utf-8")
                     for name in ("optimizer.py", "transit.py"))
    assert "road_km(" in source
    assert "travel_minutes(" in source
    assert not re.search(r"\*\s*1\.35|/\s*60\s*\*|math\.(sin|cos|asin)", source)
