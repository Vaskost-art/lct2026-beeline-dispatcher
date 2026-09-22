"""День переживает перезапуск сервиса.

Проверка идёт через настоящую базу: двойник подтвердил бы только наши
представления о ней, а вопрос тут ровно в том, поднимется ли завтра то, что
записано сегодня.
"""
import os

import pytest
from sqlalchemy import create_engine

from dispatcher.api.journal import DbJournal
from dispatcher.api.state import DayStore, DayVersion
from dispatcher.domain import Plan
from dispatcher.infrastructure.db import session as db_session
from dispatcher.infrastructure.db.base import Base
from dispatcher.services.metrics import plan_metrics
from dispatcher.services.routing import evaluate_sequence

TEST_DSN = os.environ.get(
    "DATABASE_TEST_URL",
    "postgresql+psycopg://postgres@localhost:5432/dispatcher_test")


def engine_for(dsn):
    """Отдельный движок на разовую работу со схемой."""
    return create_engine(dsn)


@pytest.fixture
def journal(monkeypatch):
    """Чистая схема и журнал, смотрящий в тестовую базу."""
    monkeypatch.setenv("DATABASE_URL", TEST_DSN)
    db_session.dispose()
    with engine_for(TEST_DSN).begin() as connection:
        Base.metadata.drop_all(connection)
        Base.metadata.create_all(connection)
    yield DbJournal()
    # Схема чистится и на выходе: версии этого теста не должны достаться
    # следующему, который проверяет сервис без построенного плана.
    with engine_for(TEST_DSN).begin() as connection:
        Base.metadata.drop_all(connection)
        Base.metadata.create_all(connection)
    db_session.dispose()


def _version(scenario, label="Расчёт", manual=False, orders_count=3):
    """Маленький, но настоящий день: одна бригада и первые заявки."""
    engineer = scenario.engineers[0]
    taken = []
    route = None
    for order in scenario.orders:
        if len(taken) >= orders_count:
            break
        if order.required_skill not in engineer.skills:
            continue
        grown, _ = evaluate_sequence(engineer, [*taken, order])
        if grown is not None:
            taken.append(order)
            route = grown
    assert route is not None and taken
    plan = Plan(routes=[route], strategy="test", solver_status="OK")
    metrics = plan_metrics(plan, scenario.orders, scenario.engineers)
    return DayVersion(label=label, plan=plan, metrics=metrics,
                      orders=list(scenario.orders),
                      engineers=list(scenario.engineers),
                      locked={taken[0].id: engineer.id}, manual=manual)


def test_day_survives_restart(journal, scenarios):
    key, scenario = next(iter(scenarios.items()))
    store = DayStore({key: scenario}, journal)
    store.push(key, _version(scenario, "Расчёт"))
    store.push(key, _version(scenario, "Передана другой бригаде", manual=True))

    # Сервис перезапустили: хранилище новое, база та же.
    revived = DayStore({}, DbJournal())
    revived.reset({key: scenario})

    day = revived.day(key)
    assert day is not None
    assert [v.label for v in day.versions] == ["Расчёт",
                                               "Передана другой бригаде"]
    current = revived.current(key)
    assert current is not None
    assert current.manual is True
    assert current.locked
    # Маршруты подняты, а не потеряны: план не пустой и совпадает по остановкам.
    assert current.plan.assigned_count == store.current(key).plan.assigned_count
    assert day.manual_labels == ["Передана другой бригаде"]


def test_step_back_is_remembered(journal, scenarios):
    key, scenario = next(iter(scenarios.items()))
    store = DayStore({key: scenario}, journal)
    store.push(key, _version(scenario, "Расчёт"))
    store.push(key, _version(scenario, "Событие дня"))
    store.step_back(key)

    revived = DayStore({}, DbJournal())
    revived.reset({key: scenario})

    day = revived.day(key)
    assert day is not None
    assert [v.label for v in day.versions] == ["Расчёт"]


def test_new_dataset_clears_the_day(journal, scenarios):
    key, scenario = next(iter(scenarios.items()))
    store = DayStore({key: scenario}, journal)
    store.push(key, _version(scenario, "Расчёт"))
    store.replace_scenario(key, scenario)

    revived = DayStore({}, DbJournal())
    revived.reset({key: scenario})

    day = revived.day(key)
    assert day is not None
    assert day.versions == []


def test_service_works_without_database(monkeypatch, scenarios):
    """Кластер не поднят - сервис работает из памяти и говорит об этом."""
    monkeypatch.setenv("DATABASE_URL",
                       "postgresql+psycopg://postgres@localhost:1/nowhere")
    db_session.dispose()
    broken = DbJournal()
    key, scenario = next(iter(scenarios.items()))
    store = DayStore({key: scenario}, broken)
    store.push(key, _version(scenario, "Расчёт"))

    assert broken.available is False
    current = store.current(key)
    assert current is not None and current.label == "Расчёт"
    db_session.dispose()
