"""Формат ответа сервиса: {ok, data} либо {ok, error}."""
import warnings

from fastapi.testclient import TestClient

from dispatcher.api.app import app

warnings.filterwarnings("ignore")


def test_successful_answer_is_wrapped():
    with TestClient(app) as client:
        answer = client.get("/api/meta")

    assert answer.status_code == 200
    payload = answer.json()
    assert payload["ok"] is True
    assert "regions" in payload["data"]
    assert "error" not in payload


def test_unknown_region_says_which_code_it_is():
    with TestClient(app) as client:
        answer = client.get("/api/scenario/нет-такого")

    assert answer.status_code == 404
    payload = answer.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "region_not_found"
    # Сообщение это готовый текст для человека, а не имя исключения.
    assert "не найден" in payload["error"]["message"]


def test_plan_not_built_is_not_the_same_as_not_found():
    """Экран должен отличать приглашение посчитать от ошибки."""
    with TestClient(app) as client:
        answer = client.get("/api/plan/vostok")

    assert answer.status_code == 409
    assert answer.json()["error"]["code"] == "plan_not_built"


def test_file_export_is_not_wrapped():
    """Выгрузка это файл: конверт сломал бы его."""
    with TestClient(app) as client:
        client.post("/api/plan", json={"region": "vostok", "strategy": "greedy"})
        answer = client.get("/api/export/vostok")

    assert answer.status_code == 200
    assert "ok" not in answer.text[:40]
