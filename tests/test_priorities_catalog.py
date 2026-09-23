"""Справочник приоритетов отдаётся полностью: и интерфейсу, и в файл набора.

Подключение идёт вторым приоритетом (постановщик, чат 19.09), и без
«Повышенной» в справочнике набор, выгруженный и загруженный обратно,
описывает не те правила, по которым строился план.
"""
import warnings

from fastapi.testclient import TestClient

from dispatcher.api.app import app
from dispatcher.domain.catalog import PRIORITIES, PRIORITY_HIGH
from dispatcher.services.dataset import scenario_to_json

warnings.filterwarnings("ignore")


def test_meta_lists_every_priority():
    with TestClient(app) as client:
        data = client.get("/api/meta").json()["data"]

    assert data["priorities"] == list(PRIORITIES)
    assert PRIORITY_HIGH in data["priorities"]


def test_dataset_file_lists_every_priority(scenarios):
    written = scenario_to_json(scenarios["vostok"])

    assert written["meta"]["reference_books"]["priorities"] == list(PRIORITIES)
