"""Как бригада добирается: пешком, на транспорте или тем и другим.

Организаторы назвали комбинированные перемещения дополнительным интересом
при оценке. Проверяется именно то, ради чего это сделано: короткое плечо
бригада проходит пешком, длинное - едет, и выбор делается по времени.
"""
import pytest

from dispatcher.domain.catalog import (
    VEHICLE_BIKE,
    VEHICLE_CAR,
    VEHICLE_FOOT,
    VEHICLE_TRANSIT,
)
from dispatcher.domain.distance import travel_minutes
from dispatcher.domain.travel import (
    MODE_TRANSIT,
    MODE_WALK,
    TRANSIT_WAIT_MIN,
    WALK_KMH,
    plan_trip,
)


def test_short_leg_is_walked():
    """Ради трёхсот метров автобус не ждут."""
    trip = plan_trip(0.3, VEHICLE_FOOT)

    assert trip.combined is False
    assert [leg.mode for leg in trip.legs] == [MODE_WALK]
    assert trip.minutes == pytest.approx(0.3 / WALK_KMH * 60, abs=1)


def test_long_leg_uses_transit_with_walking_ends():
    """Пять километров пешком не идут: подход, поездка, подход."""
    trip = plan_trip(5.0, VEHICLE_FOOT)

    assert trip.combined is True
    assert [leg.mode for leg in trip.legs] == [MODE_WALK, MODE_TRANSIT, MODE_WALK]
    assert trip.minutes < plan_trip(5.0, VEHICLE_CAR).minutes * 4
    # Ожидание транспорта входит в поездку и не теряется.
    ride = next(leg for leg in trip.legs if leg.mode == MODE_TRANSIT)
    assert ride.minutes > TRANSIT_WAIT_MIN


def test_the_faster_way_wins():
    """Выбор идёт по времени, а не по типу транспорта в карточке бригады."""
    for km in (0.2, 0.5, 1.0, 1.5, 2.0, 3.0, 8.0):
        trip = plan_trip(km, VEHICLE_FOOT)
        walked = km / WALK_KMH * 60
        assert trip.minutes <= walked + 1, f"{km} км: дольше, чем просто дойти"


def test_transit_crew_walks_when_that_is_closer():
    """У бригады на транспорте тоже есть ноги."""
    assert plan_trip(0.4, VEHICLE_TRANSIT).combined is False
    assert plan_trip(6.0, VEHICLE_TRANSIT).combined is True


def test_car_and_bike_go_straight():
    assert plan_trip(5.0, VEHICLE_CAR).combined is False
    assert plan_trip(5.0, VEHICLE_BIKE).combined is False
    assert (plan_trip(5.0, VEHICLE_CAR).minutes
            < plan_trip(5.0, VEHICLE_BIKE).minutes)


def test_zero_distance_is_zero_minutes():
    trip = plan_trip(0.0, VEHICLE_FOOT)
    assert trip.minutes == 0 and trip.legs == ()


def test_travel_minutes_uses_the_same_model():
    """Планировщик и объяснение считают дорогу одним кодом."""
    assert travel_minutes(5.0, VEHICLE_FOOT) == plan_trip(5.0, VEHICLE_FOOT).minutes


def test_text_reads_like_a_human_wrote_it():
    assert plan_trip(0.3, VEHICLE_FOOT).text.endswith("пешком")
    combined = plan_trip(6.0, VEHICLE_FOOT).text
    assert "пешком" in combined and "на транспорте" in combined


def test_walking_is_still_slower_than_driving():
    """Проверка на подмену: транспорт не должен обогнать машину."""
    for km in (1.0, 5.0, 15.0):
        assert (plan_trip(km, VEHICLE_FOOT).minutes
                > plan_trip(km, VEHICLE_CAR).minutes)
