"""Разбор файла, который диспетчер загрузил через интерфейс."""
from __future__ import annotations

import csv
import json

from dispatcher.domain.scenario import Scenario
from dispatcher.infrastructure.csvfile import decode_csv
from dispatcher.infrastructure.geo_online import Fetch
from dispatcher.infrastructure.ingest import parse_control_csv
from dispatcher.infrastructure.synthetic import parse_synthetic
from dispatcher.services.dataset.errors import DatasetError
from dispatcher.services.dataset.reader import scenario_from_json
from dispatcher.services.scenario import scenario_from_synthetic

#: Сколько событий из набора держим: интерфейс их не читает, а без предела
#: мегабайты событий уходили в каждый ответ со справочниками.
MAX_EVENTS = 20


def load_upload(filename: str, raw: bytes, region_key: str, cache_path: str,
                fetch: Fetch | None = None) -> tuple[Scenario, list[dict], str]:
    """Разбирает присланный файл; любой сбой разбора становится понятным отказом.

    `fetch` ищет координаты адресов, которых нет в кэше.
    """
    try:
        scenario, events, detected = _load(filename, raw, region_key, cache_path, fetch)
    except DatasetError:
        raise
    except RecursionError as error:
        raise DatasetError("Файл вложен слишком глубоко, это не набор данных") from error
    except (ValueError, csv.Error) as error:
        raise DatasetError(f"Файл не разобран: {error}"[:300]) from error
    return scenario, [e for e in events if isinstance(e, dict)][:MAX_EVENTS], detected


def _load(filename: str, raw: bytes, region_key: str,
          cache_path: str, fetch: Fetch | None = None) -> tuple[Scenario, list[dict], str]:
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
                "формате организаторов: Заявка;Тип заявки BK;Тип заявки HD;"
                "Начало;Окончание;Район;Адрес…")
        if "Бригада" not in header:
            # Синтетическая выгрузка организаторов, основной вход задачи:
            # исполнителей в ней нет, состав бригад собирается тем же
            # правилом, что и для встроенных участков.
            scenario = scenario_from_synthetic(
                parse_synthetic(raw, region_key, cache_path, fetch), region_name=region_key)
            if not scenario.orders:
                raise DatasetError("В CSV не нашлось ни одной заявки")
            return scenario, [], "CSV, синтетическая выгрузка организаторов"
        scenario = parse_control_csv(raw, region_key, cache_path, fetch=fetch)
        if not scenario.orders:
            raise DatasetError("В CSV не нашлось ни одной заявки")
        if not scenario.engineers:
            raise DatasetError(
                "В CSV нет колонки «Бригада» или она пустая: из такой выгрузки "
                "невозможно восстановить состав исполнителей. Загрузите набор "
                "в JSON, где исполнители заданы явно.")
        return scenario, [], "CSV, контрольная выгрузка с бригадами"

    raise DatasetError(
        "Неизвестный формат файла. Поддерживаются CSV в формате организаторов "
        "и JSON в формате набора данных - образец лежит в data/sample/.")
