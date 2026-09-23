"""Пределы и защита сервиса без входа.

Каждый случай - находка ревью безопасности: межсайтовая загрузка набора,
расчёт на отрицательный или огромный предел времени, набор на тысячи заявок,
тело запроса целиком в память до проверки размера.
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


def _dataset(orders: int) -> bytes:
    return json.dumps({
        "format": "dispatcher-dataset/1",
        "orders": [{"id": str(i), "lat": 55.75, "lon": 37.62, "address": "a",
                    "district": "d", "duration_min": 30, "window_start": "10:00",
                    "window_end": "12:00", "priority": "Обычная",
                    "required_skill": "Локальные работы"} for i in range(orders)],
        "engineers": [{"id": "e", "name": "e", "lat": 55.75, "lon": 37.62,
                       "shift_start": "09:00", "shift_end": "18:00",
                       "skills": ["Локальные работы"], "vehicle": "Автомобиль"}],
    }).encode("utf-8")


def test_write_from_another_site_is_refused(client):
    for headers in ({"Sec-Fetch-Site": "cross-site"}, {"Origin": "https://evil.example"}):
        answer = client.post("/api/dataset/upload?filename=x.json", content=_dataset(1),
                             headers=headers)
        assert answer.status_code == 403, headers
        assert answer.json()["error"]["code"] == "forbidden"


def test_same_site_write_passes(client):
    answer = client.post("/api/dataset/upload?filename=same.json", content=_dataset(2),
                         headers={"Sec-Fetch-Site": "same-origin"})
    assert answer.status_code == 200, answer.text


def test_pages_cannot_be_framed(client):
    headers = client.get("/api/meta").headers
    assert headers["x-frame-options"] == "DENY"
    assert headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("limit", ["-100", "0", "99999999999999999999"])
def test_compare_refuses_absurd_time_limits(client, limit):
    answer = client.get(f"/api/compare/vostok?time_limit_sec={limit}")
    assert answer.status_code == 422


def test_upload_refuses_a_huge_dataset(client):
    answer = client.post("/api/dataset/upload?filename=big.json", content=_dataset(401))
    assert answer.status_code == 400
    assert "400 заявок" in answer.json()["error"]["message"]


def test_upload_refuses_a_huge_body_by_its_declared_size(client):
    from dispatcher.api.routes.upload import MAX_UPLOAD_BYTES

    answer = client.post("/api/dataset/upload?filename=x.json", content=b"{}",
                         headers={"Content-Length": str(MAX_UPLOAD_BYTES + 1)})
    assert answer.status_code == 413


@pytest.mark.parametrize("patch", [{"meta": "x"}, {"orders[0].equipment": 5}])
def test_broken_fields_are_refused_or_ignored_not_crash(client, patch):
    """Битое поле набора - понятный ответ, а не 500."""
    data = json.loads(_dataset(1))
    if "meta" in patch:
        data["meta"] = patch["meta"]
    else:
        data["orders"][0]["equipment"] = 5
    answer = client.post("/api/dataset/upload?filename=broken.json",
                         content=json.dumps(data).encode("utf-8"))
    assert answer.status_code in (200, 400), answer.text


def test_meta_does_not_reveal_local_paths(client):
    text = client.get("/api/meta").text
    assert "\\\\" not in text and ":/" not in text.replace("https:/", "").replace("http:/", "")


def test_env_file_is_looked_up_in_the_project_root():
    """.env ищется в корне проекта, где его велит положить README."""
    import os

    from dispatcher.infrastructure import envfile

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert os.path.normcase(envfile.DEFAULT_PATH) == os.path.normcase(os.path.join(root, ".env"))
