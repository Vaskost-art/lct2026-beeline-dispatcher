"""Клиент стресс-теста HTTP-интерфейса: вызов, ожидание кода, аудит плана.

Счётчик обращений и список отклонений общие на весь прогон.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("STRESS_API_URL", "http://127.0.0.1:8000").rstrip("/")
REGION = "vostok"
TIME_LIMIT = int(os.environ.get("STRESS_TIME_LIMIT", "3"))

problems: list[str] = []
done = 0


def fail(label: str, what: str) -> None:
    """Отмечает провал проверки, у которой нет готового кода ответа."""
    global done
    done += 1
    problems.append(f"{label}: {what}")
    print(f"    ✗ {label}: {what}")


def unwrap(payload: object) -> object:
    """Разворачивает конверт {ok, data} либо {ok, error}.

    Проверки написаны про содержимое ответа, а не про его упаковку, поэтому
    конверт снимается в одном месте. Текст отказа кладётся под ключ
    «detail»: проверки внятности объяснения читают именно его.
    """
    if not isinstance(payload, dict) or "ok" not in payload:
        return payload
    if payload.get("ok") is True:
        return payload.get("data")
    error = payload.get("error")
    if isinstance(error, dict):
        return {"detail": error.get("message", ""), "code": error.get("code", "")}
    return payload


def call(method: str, path: str, body=None, raw: bytes | None = None,
         content_type: str = "application/json") -> tuple[int, object]:
    data = raw if raw is not None else (
        json.dumps(body, ensure_ascii=False).encode() if body is not None else None)
    safe_path = urllib.parse.quote(path, safe="/?=&%")
    request = urllib.request.Request(f"{BASE}{safe_path}", data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            text = response.read().decode("utf-8", "replace")
            return response.status, unwrap(json.loads(text) if text else None)
    except urllib.error.HTTPError as error:
        try:
            text = error.read().decode("utf-8", "replace")
        except OSError:                             # сервис ответил и закрыл соединение
            return error.code, ""
        try:
            return error.code, unwrap(json.loads(text))
        except json.JSONDecodeError:
            return error.code, text
    except Exception as error:                      # сервис не поднят, таймаут
        return 0, str(error)


def expect(label: str, method: str, path: str, codes: tuple[int, ...],
           body=None, raw: bytes | None = None,
           must_explain: bool = False) -> object:
    """Проверяет код ответа и, где это важно, наличие внятного объяснения."""
    global done
    done += 1
    status, payload = call(method, path, body=body, raw=raw)
    if status not in codes:
        problems.append(
            f"{label}: ожидали {', '.join(map(str, codes))}, получили {status} "
            f"({str(payload)[:120]})")
        print(f"    ✗ {label}: {status}")
        return payload

    if must_explain:
        detail = payload.get("detail") if isinstance(payload, dict) else None
        if not isinstance(detail, (str, list)) or not str(detail).strip():
            problems.append(f"{label}: отказ без объяснения")
            print(f"    ✗ {label}: отказ без объяснения")
            return payload
        if isinstance(detail, str) and len(detail) < 12:
            problems.append(f"{label}: объяснение слишком куцее - «{detail}»")
            print(f"    ✗ {label}: куцее объяснение")
    print(f"    · {label}: {status}")
    return payload


def plan_is_valid(label: str) -> None:
    """Главный инвариант: текущий план всегда допустим."""
    global done
    done += 1
    status, payload = call("GET", f"/api/validate/{REGION}")
    if status != 200 or not isinstance(payload, dict):
        problems.append(f"{label}: аудит не ответил ({status})")
        print(f"    ✗ {label}: аудит не ответил")
        return
    if not payload.get("ok"):
        problems.append(f"{label}: план нарушает ограничения - {payload.get('by_rule')}")
        print(f"    ✗ {label}: план невалиден")
        return
    print(f"    · {label}: план допустим ({payload['checked_stops']} визитов)")


def tick() -> None:
    """Засчитывает проверку, сделанную в обход `expect`."""
    global done
    done += 1
