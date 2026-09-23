#!/usr/bin/env python3
"""Стресс-тест HTTP-интерфейса: битые запросы и нарушенный порядок вызовов.

Проверяется не «работает ли счастливый путь» - это делают selftest.py и
stress.py, - а то, что сервис на любое кривое обращение отвечает понятным
кодом и текстом, а не пятисоткой и не молчаливым согласием.

Отдельно проверяется главный инвариант: после ЛЮБОЙ последовательности
вызовов текущий план остаётся допустимым по встроенному аудиту.

    python -m uvicorn dispatcher.api.app:app --app-dir src --port 8000
    python scripts/stress_api.py              # в другом терминале

Код возврата 0 - все ветки ответили как ожидалось.
"""
from __future__ import annotations

import stress_api_client as client
from stress_api_client import BASE, call
from stress_api_day import adjustments, risk_upload_export, undo_and_save
from stress_api_plan import basics, explain_and_reassign, planning, replanning


def main() -> int:
    status, meta = call("GET", "/api/meta")
    if status != 200:
        print(f"Сервис не отвечает на {BASE} - запустите его и повторите.")
        return 2
    print(f"Сервис на {BASE}, районов: {len(meta['regions'])}\n")

    basics()
    day = planning()
    explain_and_reassign(day)
    replanning(day)
    adjustments(day)
    undo_and_save()
    risk_upload_export()

    print()
    print("=" * 74)
    print(f"Обращений к API проверено: {client.done}")
    problems = client.problems
    if problems:
        print(f"НАЙДЕНО ОТКЛОНЕНИЙ: {len(problems)}\n")
        for item in problems:
            print(f"  · {item}")
        return 1
    print("Отклонений нет: на каждое кривое обращение сервис отвечает понятно, "
          "а план остаётся допустимым.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
