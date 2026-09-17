"""Общие фикстуры тестов."""
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(ROOT, "data", "raw")
CACHE = os.path.join(ROOT, "data", "geo_cache.json")


@pytest.fixture(scope="session")
def scenarios():
    """Все участки, загруженные из выгрузок заказчика."""
    from dispatcher.services.scenario import load_all

    return load_all(RAW_DIR, CACHE)
