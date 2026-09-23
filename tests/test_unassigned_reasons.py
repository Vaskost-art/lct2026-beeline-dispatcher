"""Причина отказа называет препятствие поимённо.

Текст «транспорта нет или навыка нет» не говорил диспетчеру, кому дать
машину, а кому допуск: на «Востоке» машины были у бригад без допуска к
авариям, а допуск у бригады без машины.
"""
from dispatcher.domain import Engineer, Order
from dispatcher.domain.catalog import (
    SKILL_EMERGENCY,
    SKILL_LOCAL,
    VEHICLE_CAR,
    VEHICLE_TRANSIT,
)
from dispatcher.services.planning.reasons import diagnose

LAT, LON = 55.75, 37.62


def _crew(crew_id: str, skills: list[str], vehicle: str) -> Engineer:
    return Engineer(id=crew_id, name=f"Бригада {crew_id}", lat=LAT, lon=LON,
                    start_address="", shift_start=9 * 60, shift_end=18 * 60,
                    skills=skills, vehicle=vehicle)


EMERGENCY = Order(id="a1", lat=LAT, lon=LON, address="", district="",
                  duration_min=60, window_start=10 * 60, window_end=12 * 60,
                  priority="Срочная", required_skill=SKILL_EMERGENCY,
                  required_vehicle=VEHICLE_CAR)


def test_vehicle_refusal_names_who_lacks_what():
    crews = [_crew("5", [SKILL_EMERGENCY], VEHICLE_TRANSIT),
             _crew("1", [SKILL_LOCAL], VEHICLE_CAR),
             _crew("2", [SKILL_LOCAL], VEHICLE_CAR)]

    text = diagnose(EMERGENCY, crews).reason_text

    assert "Бригада 5" in text
    assert "Бригада 1, Бригада 2" in text
    assert " или " not in text


def test_vehicle_refusal_says_nobody_has_it():
    text = diagnose(EMERGENCY, [_crew("5", [SKILL_EMERGENCY], VEHICLE_TRANSIT)]).reason_text

    assert "нет ни у одной бригады" in text
