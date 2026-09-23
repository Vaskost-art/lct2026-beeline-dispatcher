"""Защита сервиса без входа, второй круг ревью.

Каждый случай подтверждён вживую: перепривязка чужого домена на 127.0.0.1,
страница на другом порту этой же машины, расчёт, занятый картинкой с чужого
сайта, длинное имя файла, выключавшее журнал для всех участков, и сбои
разбора, отдававшие голый 500.
"""
import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from dispatcher.api import deps
    from dispatcher.api.app import app

    deps.JOURNAL.available = False
    with TestClient(app) as test_client:
        yield test_client


def test_foreign_host_name_is_refused_even_for_reading(client):
    answer = client.get("/api/meta", headers={"Host": "evil.example:8000"})
    assert answer.status_code == 403
    assert answer.headers["X-Frame-Options"] == "DENY"


@pytest.mark.parametrize("site", ["same-site", "cross-site"])
def test_other_sites_neither_read_nor_write(client, site):
    assert client.get("/api/compare/vostok", headers={"Sec-Fetch-Site": site}).status_code == 403
    answer = client.post("/api/plan/save", json={"region": "vostok"},
                         headers={"Sec-Fetch-Site": site})
    assert answer.status_code == 403


def test_origin_with_another_port_is_refused(client):
    answer = client.post("/api/plan/save", json={"region": "vostok"},
                         headers={"Origin": "http://testserver:9999"})
    assert answer.status_code == 403


def test_the_page_itself_is_served(client):
    assert client.get("/api/meta", headers={"Sec-Fetch-Site": "same-origin"}).status_code == 200


def test_huge_body_of_an_ordinary_route_is_refused(client):
    answer = client.post("/api/explain", content=b"{}",
                         headers={"Content-Length": str(2 * 1024 * 1024)})
    assert answer.status_code == 413


def test_long_file_name_gives_a_short_region_key():
    from dispatcher.api.routes.upload import MAX_KEY, region_key_for

    key = region_key_for("Выгрузка_заявок_Юго-Восток_17_08_2026_контрольная_final" * 3 + ".csv")
    assert len(key) <= MAX_KEY
    assert key != region_key_for("Выгрузка_заявок_Юго-Восток_17_08_2026" * 3 + ".csv")


@pytest.mark.parametrize("body", [
    b"[" * 200_000 + b"]" * 200_000,
    b'{"orders": [{"lat": ' + b"9" * 5000 + b"}]}",
], ids=["deep", "long-number"])
def test_broken_json_is_a_clear_refusal(client, body):
    answer = client.post("/api/dataset/upload?filename=x.json", content=body)
    assert answer.status_code == 400, answer.text[:200]
    assert answer.json()["ok"] is False


def test_restore_under_a_dirty_key_registers_nothing(client):
    answer = client.post("/api/plan/restore", json={"region": "vostok!"})
    assert answer.status_code in (400, 404)
    regions = [r["region_key"] for r in client.get("/api/meta").json()["data"]["regions"]]
    assert "vostok!" not in regions


def test_absurd_duration_is_refused(client):
    data = json.dumps({"orders": [{"id": "a", "lat": 55.7, "lon": 37.6,
                                   "duration_min": 10 ** 30, "window_start": "10:00",
                                   "window_end": "12:00", "required_skill": "Локальные работы"}],
                       "engineers": [{"id": "e", "lat": 55.7, "lon": 37.6,
                                      "shift_start": "09:00", "shift_end": "18:00",
                                      "skills": ["Локальные работы"]}]}).encode()
    answer = client.post("/api/dataset/upload?filename=d.json", content=data)
    assert answer.status_code == 400
