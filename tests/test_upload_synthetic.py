"""Загрузка синтетической выгрузки организаторов - основного входа задачи.

Раньше CSV без колонки «Бригада» отвергался с советом загрузить JSON, то есть
файл в том виде, в каком его выдали организаторы, сервис не принимал.
"""
import os

from dispatcher.infrastructure.csvfile import decode_csv
from dispatcher.infrastructure.synthetic import OFFICE_MARKER
from dispatcher.services.dataset import load_upload

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw", "vostok_synth.csv")
CACHE = os.path.join(ROOT, "data", "geo_cache.json")


def _raw() -> bytes:
    with open(RAW, "rb") as fh:
        return fh.read()


def test_synthetic_csv_gets_crews_from_office():
    scenario, _, kind = load_upload("vostok_synth.csv", _raw(), "upload-test", CACHE)

    assert "синтетическая" in kind
    assert len(scenario.orders) == 66
    assert scenario.engineers
    assert all(crew.lat and crew.lon for crew in scenario.engineers)


def test_synthetic_csv_without_office_starts_near_orders():
    lines = decode_csv(_raw()).split("\n")
    kept = [line for line in lines if OFFICE_MARKER not in line.lower()]
    assert len(kept) < len(lines)
    raw = "\n".join(kept).encode("utf-8")

    scenario, _, _ = load_upload("v.csv", raw, "upload-test", CACHE)

    crew = scenario.engineers[0]
    lats = [order.lat for order in scenario.orders]
    assert min(lats) <= crew.lat <= max(lats)


def test_office_line_is_not_a_skipped_order():
    """Строка офиса в хвосте выгрузки - не наряд с битым временем."""
    scenario, _, _ = load_upload("vostok_synth.csv", _raw(), "upload-test", CACHE)

    assert scenario.skipped_rows == []
