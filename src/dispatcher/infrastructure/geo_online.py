"""Поиск координат через HTTP Геокодер Яндекса для адресов, которых нет в кэше.

Эталонный кэш `data/geo_cache.json` собирается заранее скриптом и сервисом не
меняется. Адреса загруженного файла, которых в нём нет, сервис ищет сам, если
задан ключ YANDEX_GEOCODER_API_KEY, и дописывает в локальный кэш рядом с
эталонным. Без ключа или при сбое сети адрес остаётся на центре района, как и
раньше: загрузка не падает и не ждёт дольше предела.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, wait

from dispatcher.domain.distance import normalize_address
from dispatcher.infrastructure.geo import Geocoder, local_cache_path, read_cache
from dispatcher.infrastructure.geo_queries import build_query, fallback_queries

log = logging.getLogger(__name__)

#: Запрос к геокодеру: строка адреса -> (широта, долгота) или None.
Fetch = Callable[[str], "tuple[float, float] | None"]
#: Кэш-запись: координаты, запрос и источник.
Entry = dict[str, float | str | None]

YANDEX_GEOCODER = "https://geocode-maps.yandex.ru/1.x/"
USER_AGENT = "dispatcher-route-planner/1.0 (field service routing prototype)"
#: Ответа на один запрос ждём недолго: зависший геокодер не должен держать
#: загрузку файла.
REQUEST_TIMEOUT_SEC = 5
#: Весь поиск по файлу укладывается в этот предел; что не успели, остаётся на
#: центре района.
BUDGET_SEC = 25
#: Параллельных запросов: сотня адресов за несколько секунд, не больше того,
#: что Яндекс пропускает без отказов.
WORKERS = 8


def yandex_fetch(api_key: str) -> Fetch:
    """Запрос к Яндексу с этим ключом. Любой сбой сети или ответа даёт None.

    Отклонённый ключ отключает все следующие запросы этого поиска: сотня
    заведомых отказов только тянула бы загрузку и засоряла журнал.
    """
    key_rejected = threading.Event()

    def fetch(query: str) -> tuple[float, float] | None:
        if key_rejected.is_set():
            return None
        params = urllib.parse.urlencode({
            "apikey": api_key, "geocode": query, "format": "json",
            "results": 1, "lang": "ru_RU",
        })
        request = urllib.request.Request(f"{YANDEX_GEOCODER}?{params}",
                                         headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SEC) as resp:
                data = json.load(resp)
            members = data["response"]["GeoObjectCollection"]["featureMember"]
            if not members:
                return None
            lon, lat = members[0]["GeoObject"]["Point"]["pos"].split()
            return float(lat), float(lon)
        except urllib.error.HTTPError as error:
            # 401/403 значит ключ: без этой записи отказ неотличим от
            # «адреса нет», и неверный ключ живёт незамеченным.
            if error.code in (401, 403) and not key_rejected.is_set():
                key_rejected.set()
                log.warning("Геокодер отклонил ключ YANDEX_GEOCODER_API_KEY: HTTP %s",
                            error.code)
            return None
        except Exception:  # noqa: BLE001 - сеть, лимит, чужой ответ: адрес останется приблизительным
            return None
    return fetch


def resolve(address: str, district: str, fetch: Fetch) -> Entry | None:
    """Координата адреса: сначала как есть, потом всё грубее, до одной улицы."""
    query = build_query(address, district)
    for attempt in [query, *fallback_queries(query)]:
        coords = fetch(attempt)
        if coords:
            source = "yandex" if attempt == query else "yandex_coarse"
            return {"lat": coords[0], "lon": coords[1], "query": attempt,
                    "source": source}
    return None


def fill_missing(geocoder: Geocoder, places: Iterable[tuple[str, str]],
                 fetch: Fetch, budget_sec: float = BUDGET_SEC) -> int:
    """Ищет адреса, которых нет в кэше геокодера. Возвращает, сколько нашёл."""
    todo: dict[str, tuple[str, str]] = {}
    for address, district in places:
        key = normalize_address(address)
        if key and key not in todo and not geocoder.knows(key):
            todo[key] = (address, district)
    if not todo:
        return 0

    pool = ThreadPoolExecutor(max_workers=WORKERS)
    jobs = {pool.submit(resolve, address, district, fetch): key
            for key, (address, district) in todo.items()}
    done, _ = wait(jobs, timeout=budget_sec)
    pool.shutdown(wait=False, cancel_futures=True)

    found: dict[str, Entry] = {}
    for job in done:
        if job.exception() is None and (value := job.result()) is not None:
            found[jobs[job]] = value
    if found:
        geocoder.remember(found)
        _store_local(geocoder.cache_path, found)
    return len(found)


#: Две загрузки файла могут дописывать локальный кэш одновременно.
_LOCAL_WRITE = threading.Lock()


def _store_local(cache_path: str, found: dict[str, Entry]) -> None:
    """Дописывает найденное в локальный кэш: повторная загрузка не ищет заново."""
    path = local_cache_path(cache_path)
    with _LOCAL_WRITE:
        stored = {**read_cache(path), **found}
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(stored, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
