"""Вырожденные и граничные наборы данных для стресс-теста."""
from __future__ import annotations

from dispatcher.domain import Engineer, Order, catalog, norms

BASE_LAT, BASE_LON = 55.75, 37.62


def order(oid: str, *, lat: float = BASE_LAT, lon: float = BASE_LON,
          duration: int = 60, start: int = 10 * 60, end: int = 12 * 60,
          skill: str = catalog.SKILL_LOCAL, vehicle: str | None = None,
          priority: str = catalog.PRIORITY_NORMAL, district: str = "Тестовый") -> Order:
    return Order(id=oid, lat=lat, lon=lon, address=f"Адрес {oid}", district=district,
                 duration_min=duration, window_start=start, window_end=end,
                 priority=priority, required_skill=skill, required_vehicle=vehicle,
                 type_bk="Локальная заявка", type_hd="Нет линка")


def engineer(eid: str, *, lat: float = BASE_LAT, lon: float = BASE_LON,
             shift: tuple[int, int] = (9 * 60, 22 * 60),
             skills: list[str] | None = None,
             vehicle: str = catalog.VEHICLE_CAR) -> Engineer:
    return Engineer(id=eid, name=eid, lat=lat, lon=lon,
                    start_address="База", shift_start=shift[0], shift_end=shift[1],
                    skills=skills or [catalog.SKILL_LOCAL], vehicle=vehicle)


def case(name: str, orders: list[Order], engineers: list[Engineer]) -> tuple:
    return (name, orders, engineers)


def build_cases() -> list[tuple]:
    """Вырожденные и граничные наборы данных."""
    all_skills = list(dict.fromkeys(norms.SKILL_BY_TYPE_BK.values()))
    cases = [
        case("пустой набор", [], [engineer("E1")]),
        case("нет исполнителей", [order("O1")], []),
        case("пусто и там и там", [], []),
        case("одна заявка, один исполнитель", [order("O1")], [engineer("E1")]),

        case("все заявки в одной точке",
             [order(f"O{i}", duration=30) for i in range(1, 9)],
             [engineer("E1"), engineer("E2")]),

        case("заявки за сотни километров",
             [order("O1", lat=55.75, lon=37.62),
              order("O2", lat=54.84, lon=38.16, start=11 * 60, end=13 * 60),
              order("O3", lat=56.30, lon=36.70, start=12 * 60, end=14 * 60)],
             [engineer("E1")]),

        case("окно короче длительности работ",
             [order("O1", duration=180, start=10 * 60, end=10 * 60 + 30)],
             [engineer("E1")]),

        case("длительность больше смены",
             [order("O1", duration=900)],
             [engineer("E1", shift=(9 * 60, 18 * 60))]),

        case("смена длиной в минуту",
             [order("O1")],
             [engineer("E1", shift=(10 * 60, 10 * 60 + 1))]),

        case("круглосуточное окно",
             [order(f"O{i}", start=1, end=23 * 60 + 59) for i in range(1, 5)],
             [engineer("E1")]),

        case("окно ровно равно длительности",
             [order("O1", duration=120, start=10 * 60, end=12 * 60)],
             [engineer("E1")]),

        case("ни у кого нет нужного навыка",
             [order("O1", skill=catalog.SKILL_EMERGENCY)],
             [engineer("E1", skills=[catalog.SKILL_LOCAL])]),

        case("нужен автомобиль, все пешком",
             [order("O1", vehicle=catalog.VEHICLE_CAR)],
             [engineer("E1", vehicle=catalog.VEHICLE_FOOT)]),

        case("все заявки срочные",
             [order(f"O{i}", priority=catalog.PRIORITY_URGENT,
                    lat=BASE_LAT + i * 0.01) for i in range(1, 11)],
             [engineer("E1"), engineer("E2")]),

        case("все заявки в одно окно, людей не хватает",
             [order(f"O{i}", duration=90, start=10 * 60, end=12 * 60,
                    lat=BASE_LAT + i * 0.02) for i in range(1, 13)],
             [engineer("E1")]),

        case("исполнителей больше, чем заявок",
             [order("O1")],
             [engineer(f"E{i}") for i in range(1, 16)]),

        case("три навыка у одного, по одному у прочих",
             [order(f"O{i}", skill=all_skills[i % 3], lat=BASE_LAT + i * 0.005)
              for i in range(1, 10)],
             [engineer("E-все", skills=all_skills)]
             + [engineer(f"E{i}", skills=[all_skills[i]]) for i in range(3)]),

        case("все типы транспорта",
             [order(f"O{i}", lat=BASE_LAT + i * 0.004) for i in range(1, 9)],
             [engineer(f"E-{v}", vehicle=v) for v in catalog.VEHICLES]),

        case("смены не пересекаются с окнами",
             [order("O1", start=10 * 60, end=12 * 60)],
             [engineer("E1", shift=(18 * 60, 22 * 60))]),

        case("смена начинается после конца окна",
             [order("O1", start=8 * 60, end=9 * 60)],
             [engineer("E1", shift=(20 * 60, 23 * 60))]),

        case("координаты на экваторе и нулевом меридиане",
             [order("O1", lat=0.0, lon=0.0), order("O2", lat=0.01, lon=0.01)],
             [engineer("E1", lat=0.0, lon=0.0)]),

        case("отрицательные координаты",
             [order("O1", lat=-33.87, lon=-70.65),
              order("O2", lat=-33.88, lon=-70.66)],
             [engineer("E1", lat=-33.87, lon=-70.65)]),

        case("спецсимволы и юникод в идентификаторах",
             [order("O-1/2«тест»", district="Район «Северный»"),
              order("O\t2\n", district="Район 🚐")],
             [engineer("Бригада «Смирнов» & Co.")]),

        case("очень длинные строки",
             [order("O" + "1" * 300, district="Р" * 500)],
             [engineer("E" + "2" * 300)]),

        case("сто заявок, пятнадцать исполнителей",
             [order(f"O{i}", duration=45,
                    start=(9 + i % 12) * 60, end=(11 + i % 12) * 60,
                    lat=BASE_LAT + (i % 10) * 0.01, lon=BASE_LON + (i // 10) * 0.01,
                    skill=all_skills[i % 3],
                    priority=catalog.PRIORITY_URGENT if i % 7 == 0
                             else catalog.PRIORITY_NORMAL)
              for i in range(1, 101)],
             [engineer(f"E{i}", skills=all_skills[: 1 + i % 3],
                       vehicle=list(catalog.VEHICLES)[i % 4],
                       shift=(8 * 60 + i * 10, 20 * 60 + i * 5))
              for i in range(1, 16)]),
    ]
    return cases
