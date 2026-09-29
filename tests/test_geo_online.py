"""Адреса загруженного файла, которых нет в кэше, ищет геокодер на лету.

Без этого чужой файл целиком вставал в центры районов: план формально верный,
но пробег и порядок объезда выдуманы. Геокодер здесь подменён, в сеть тесты
не ходят.
"""
import json
import os
import time

from dispatcher.infrastructure.geo import (
    PRECISION_APPROX,
    PRECISION_EXACT,
    Geocoder,
    local_cache_path,
)
from dispatcher.infrastructure.geo_online import fill_missing
from dispatcher.services.dataset.upload import load_upload

LAT, LON = 55.705, 37.737    # Текстильщики

HEADER = "Заявка;Тип заявки BK;Статус BK;Тип заявки HD;Начало;Окончание;Район;Адрес"
ROWS = [
    "1;Подключение;Отправлена;Конвергенция абонента;28.09.2026 12:00;28.09.2026 14:00;"
    "Текстильщики;Город Москва, ул.Артюхиной, д. 16",
    "2;Ремонт;Отправлена;Ремонт;28.09.2026 14:00;28.09.2026 16:00;"
    "Текстильщики;Город Москва, ул.Малышева, д. 13",
]


def _csv() -> bytes:
    return "\r\n".join([HEADER, *ROWS]).encode("cp1251")


def _cache(tmp_path) -> str:
    path = tmp_path / "geo_cache.json"
    path.write_text("{}", encoding="utf-8")
    return str(path)


def _read(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def test_uploaded_file_gets_real_coordinates(tmp_path):
    cache = _cache(tmp_path)
    asked: list[str] = []

    def fetch(query):
        asked.append(query)
        return LAT + len(asked) / 1000, LON

    scenario, _, _ = load_upload("day.csv", _csv(), "day", cache, fetch)

    assert {o.geocode_precision for o in scenario.orders} == {PRECISION_EXACT}
    assert scenario.geo_report["fetched"] == 2
    # Эталонный кэш не трогаем: найденное лежит в локальном рядом.
    assert _read(cache) == {}
    assert len(_read(local_cache_path(cache))) == 2

    # Повторная загрузка того же файла берёт координаты из локального кэша.
    asked.clear()
    again, _, _ = load_upload("day.csv", _csv(), "day", cache, fetch)
    assert asked == []
    assert {o.geocode_precision for o in again.orders} == {PRECISION_EXACT}


def test_without_geocoder_addresses_stay_on_district_centre(tmp_path):
    scenario, _, _ = load_upload("day.csv", _csv(), "day", _cache(tmp_path))

    assert {o.geocode_precision for o in scenario.orders} == {PRECISION_APPROX}
    assert not os.path.exists(local_cache_path(str(tmp_path / "geo_cache.json")))


def test_failing_geocoder_does_not_break_the_upload(tmp_path):
    def broken(query):
        raise OSError("сеть недоступна")

    scenario, _, _ = load_upload("day.csv", _csv(), "day", _cache(tmp_path), broken)

    assert len(scenario.orders) == 2
    assert {o.geocode_precision for o in scenario.orders} == {PRECISION_APPROX}


def test_slow_geocoder_is_cut_by_the_budget(tmp_path):
    geocoder = Geocoder(_cache(tmp_path))

    def slow(query):
        time.sleep(2)
        return LAT, LON

    started = time.monotonic()
    found = fill_missing(geocoder, [("ул.Артюхиной, д. 16", "Текстильщики")], slow,
                         budget_sec=0.2)
    assert found == 0
    assert time.monotonic() - started < 1.5


def test_query_keeps_street_words_and_house_block():
    from dispatcher.infrastructure.geo_queries import build_query

    assert build_query("пер.1-й Гончарный, д. 7", "Таганский") == "переулок 1-й Гончарный, 7"
    assert build_query("ул.Ташкентская, д. 4 к 2", "Выхино") == "улица Ташкентская, 4 к2"


def test_rejected_key_stops_further_requests(monkeypatch):
    import urllib.error

    from dispatcher.infrastructure import geo_online

    calls: list[str] = []

    def refuse(request, timeout):
        calls.append(request.full_url)
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(geo_online.urllib.request, "urlopen", refuse)
    fetch = geo_online.yandex_fetch("wrong-key")

    assert fetch("Москва, улица Артюхиной, 16") is None
    assert fetch("Москва, улица Малышева, 13") is None
    assert len(calls) == 1
