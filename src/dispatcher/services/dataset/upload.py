"""Разбор файла, который диспетчер загрузил через интерфейс."""
from __future__ import annotations

import json

from dispatcher.domain.scenario import Scenario
from dispatcher.infrastructure.csvfile import decode_csv
from dispatcher.infrastructure.ingest import parse_control_csv
from dispatcher.services.dataset.errors import DatasetError
from dispatcher.services.dataset.reader import scenario_from_json


def load_upload(filename: str, raw: bytes, region_key: str,
                cache_path: str) -> tuple[Scenario, list[dict], str]:
    """Разбирает присланный файл, сам определяя формат.

    Возвращает (сценарий, события, описание распознанного формата).
    """
    if not raw.strip():
        raise DatasetError("Файл пустой")

    name = (filename or "").lower()
    head = raw[:4096].lstrip()

    # JSON узнаём по первому непробельному символу, а не только по расширению
    if head[:1] in (b"{", b"[") or name.endswith(".json"):
        try:
            data = json.loads(raw.decode("utf-8-sig"))
        except UnicodeDecodeError as error:
            raise DatasetError("JSON должен быть в кодировке UTF-8") from error
        except json.JSONDecodeError as exc:
            raise DatasetError(f"Не удалось разобрать JSON: {exc.msg} "
                               f"(строка {exc.lineno}, символ {exc.colno})") from exc
        scenario, events = scenario_from_json(data, region_key)
        return scenario, events, "JSON, формат набора данных"

    if name.endswith(".csv") or b";" in head:
        text = decode_csv(raw)
        header = text.split("\n", 1)[0]
        if "Заявка" not in header:
            raise DatasetError(
                "В CSV не найдена колонка «Заявка». Ожидается выгрузка в "
                "формате организаторов: Заявка;Тип заявки BK;Статус BK;"
                "Тип заявки HD;Начало;Окончание;Район;Адрес;Бригада…")
        scenario = parse_control_csv(raw, region_key, cache_path)
        if not scenario.orders:
            raise DatasetError("В CSV не нашлось ни одной заявки")
        if not scenario.engineers:
            raise DatasetError(
                "В CSV нет колонки «Бригада» или она пустая: из такой выгрузки "
                "невозможно восстановить состав исполнителей. Загрузите набор "
                "в JSON, где исполнители заданы явно.")
        return scenario, [], "CSV, выгрузка в формате организаторов"

    raise DatasetError(
        "Неизвестный формат файла. Поддерживаются CSV в формате организаторов "
        "и JSON в формате набора данных — образец лежит в data/sample/.")
