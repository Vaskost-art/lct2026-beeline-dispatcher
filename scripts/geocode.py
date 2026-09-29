#!/usr/bin/env python3
"""Разовое геокодирование адресов.

Запускается ОДИН РАЗ на машине с интернетом, результат - `data/geo_cache.json` -
коммитится в репозиторий. После этого прототип и демонстрация работают офлайн.

Два источника координат:

  «Яндекс»    - HTTP Геокодер Яндекса, российский сервис. Нужен ключ
                в переменной YANDEX_GEOCODER_API_KEY. Используется
                по умолчанию, если ключ задан.
  «Nominatim» - OpenStreetMap, без ключа. Запасной вариант.

    export YANDEX_GEOCODER_API_KEY="ваш-ключ"
    python3 scripts/geocode.py                     # догеокодировать недостающее
    python3 scripts/geocode.py --provider nominatim
    python3 scripts/geocode.py --force             # перегеокодировать всё

Адреса берутся из выгрузок `data/raw` и из дополнительных дней
`data/extra`. Около 700 уникальных адресов: у Яндекса несколько минут, у
Nominatim дольше - он просит не чаще одного запроса в секунду.
"""
from __future__ import annotations

import argparse
import csv
import glob
import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from dispatcher.domain.distance import normalize_address  # noqa: E402
from dispatcher.infrastructure import envfile  # noqa: E402
from dispatcher.infrastructure.csvfile import (  # noqa: E402
    CSV_DELIMITER,
    _clean_address,
    decode_csv,
)
from dispatcher.infrastructure.geo_online import yandex_fetch  # noqa: E402
from dispatcher.infrastructure.geo_queries import build_query, fallback_queries  # noqa: E402

NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "dispatcher-route-planner/1.0 (field service routing prototype)"

# Nominatim просит не чаще одного запроса в секунду; у Яндекса лимит мягче.
RATE_LIMIT_SEC = {"nominatim": 1.1, "yandex": 0.25}

DATA_FILES = (os.path.join(ROOT, "data", "raw", "*.csv"),
              os.path.join(ROOT, "data", "extra", "*.csv"))
CACHE_PATH = os.path.join(ROOT, "data", "geo_cache.json")



def _request(url: str) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.load(resp)
    except Exception as exc:                      # сеть, лимит, таймаут
        print(f"    ! {exc}")
        return None


def geocode_nominatim(query: str, _key: str) -> tuple[float, float] | None:
    """Первый ответ геокодера на адрес.

    Берём несколько вариантов, а не один: улица с тем же названием есть
    и в соседнем городе, и при `limit=1` в кэш однажды попала «улица
    Талалихина» из Щербинки вместо Таганского района. Правдоподобность
    выбранной точки проверяет `dispatcher/infrastructure/geo.py` при чтении кэша.
    """
    params = urllib.parse.urlencode({
        "q": query, "format": "json", "limit": 5, "countrycodes": "ru",
    })
    data = _request(f"{NOMINATIM}?{params}")
    if not data:
        return None
    return float(data[0]["lat"]), float(data[0]["lon"])


def geocode_yandex(query: str, api_key: str) -> tuple[float, float] | None:
    """HTTP Геокодер Яндекса: тот же запрос, что делает сервис при загрузке файла."""
    return yandex_fetch(api_key)(query)


def collect_addresses() -> list[tuple[str, str, str]]:
    """Уникальные (ключ, исходный адрес, район) из всех выгрузок проекта."""
    seen: dict[str, tuple[str, str, str]] = {}
    for pattern in DATA_FILES:
        for path in sorted(glob.glob(pattern)):
            with open(path, "rb") as fh:
                text = decode_csv(fh.read())
            for row in csv.DictReader(io.StringIO(text), delimiter=CSV_DELIMITER):
                if not (row.get("Заявка") or "").strip():
                    continue
                address = _clean_address(row.get("Адрес") or "")
                key = normalize_address(address)
                if key and key not in seen:
                    seen[key] = (key, address, (row.get("Район") or "").strip())
    return list(seen.values())


PROVIDERS = {"yandex": geocode_yandex, "nominatim": geocode_nominatim}
PROVIDER_TITLES = {"yandex": "Яндекс Геокодер", "nominatim": "OpenStreetMap/Nominatim"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="перегеокодировать адреса, уже лежащие в кэше")
    ap.add_argument("--provider", choices=sorted(PROVIDERS), default=None,
                    help="источник координат; по умолчанию Яндекс, "
                         "если задан YANDEX_GEOCODER_API_KEY")
    args = ap.parse_args()

    # Ключ можно задать и через окружение, и через .env рядом с проектом.
    envfile.load()
    api_key = os.environ.get("YANDEX_GEOCODER_API_KEY", "").strip()
    provider = args.provider or ("yandex" if api_key else "nominatim")
    if provider == "yandex" and not api_key:
        print("Для Яндекс Геокодера нужен ключ YANDEX_GEOCODER_API_KEY - "
              "положите его в файл .env рядом с проектом (образец в "
              ".env.example) или задайте переменной окружения.")
        print("Без ключа можно обойтись: "
              "python3 scripts/geocode.py --provider nominatim")
        return 2
    geocode_one = PROVIDERS[provider]
    delay = RATE_LIMIT_SEC[provider]
    print(f"Источник координат: {PROVIDER_TITLES[provider]}")

    cache: dict[str, dict] = {}
    if os.path.exists(CACHE_PATH) and not args.force:
        with open(CACHE_PATH, encoding="utf-8") as fh:
            cache = json.load(fh)

    targets = collect_addresses()
    todo = [t for t in targets if t[0] not in cache or cache[t[0]].get("lat") is None]
    print(f"Всего уникальных адресов: {len(targets)}; к геокодированию: {len(todo)}")

    ok = 0
    coarse = 0
    for i, (key, address, district) in enumerate(todo, 1):
        query = build_query(address, district)
        print(f"[{i}/{len(todo)}] {query}")
        coords = geocode_one(query, api_key)
        time.sleep(delay)
        used = query
        for alt in (fallback_queries(query) if not coords else []):
            print(f"    ~ не нашёлся, пробую грубее: {alt}")
            coords = geocode_one(alt, api_key)
            time.sleep(delay)
            if coords:
                used = alt
                break
        if coords:
            exact = used == query
            cache[key] = {"lat": coords[0], "lon": coords[1], "query": used,
                          "source": provider if exact else f"{provider}_coarse"}
            ok += 1
            coarse += 0 if exact else 1
            note = "" if exact else "  (по упрощённому адресу)"
            print(f"    -> {coords[0]:.6f}, {coords[1]:.6f}{note}")
        else:
            cache[key] = {"lat": None, "lon": None, "query": query,
                          "source": "not_found"}
            print("    -> не найден, останется приблизительная точка района")
        if i == 10 and ok == 0:
            # Десять подряд мимо - это ключ или сеть, а не адреса: не портим кэш.
            print("Первые 10 адресов не нашлись: проверьте ключ и сеть. Кэш не изменён.")
            return 3
        if i % 20 == 0:
            with open(CACHE_PATH, "w", encoding="utf-8") as fh:
                json.dump(cache, fh, ensure_ascii=False, indent=1)

    with open(CACHE_PATH, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False, indent=1)
    resolved = sum(1 for v in cache.values() if v.get("lat") is not None)
    coarse_note = ""
    if coarse:
        coarse_note = (f" (из них {coarse} по упрощённому адресу: точка на "
                       f"нужной улице, но без корпуса или строения)")
    print(f"\nГотово. Найдено в этом запуске: {ok}{coarse_note}. "
          f"Всего координат в кэше: {resolved}/{len(targets)} "
          f"({resolved / max(len(targets), 1) * 100:.0f}%)")
    print(f"Кэш: {CACHE_PATH} - закоммитьте его в репозиторий.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
