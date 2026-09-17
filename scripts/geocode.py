#!/usr/bin/env python3
"""Разовое геокодирование адресов.

Запускается ОДИН РАЗ на машине с интернетом, результат — `data/geo_cache.json` —
коммитится в репозиторий. После этого прототип и демонстрация работают офлайн.

Два источника координат:

  «Яндекс»    — HTTP Геокодер Яндекса, российский сервис. Нужен ключ
                в переменной YANDEX_GEOCODER_API_KEY. Используется
                по умолчанию, если ключ задан.
  «Nominatim» — OpenStreetMap, без ключа. Запасной вариант.

    export YANDEX_GEOCODER_API_KEY="ваш-ключ"
    python3 scripts/geocode.py                     # догеокодировать недостающее
    python3 scripts/geocode.py --provider nominatim
    python3 scripts/geocode.py --force             # перегеокодировать всё

Около 200 уникальных адресов: у Яндекса примерно минута, у Nominatim около
четырёх — он просит не чаще одного запроса в секунду.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

import envfile  # noqa: E402

from dispatcher.domain.distance import normalize_address, normalize_district  # noqa: E402
from dispatcher.infrastructure.csvfile import (  # noqa: E402
    CSV_DELIMITER,
    RAW_ENCODING,
    _clean_address,
)
from dispatcher.infrastructure.ingest import REGIONS  # noqa: E402

NOMINATIM = "https://nominatim.openstreetmap.org/search"
YANDEX_GEOCODER = "https://geocode-maps.yandex.ru/1.x/"
USER_AGENT = "dispatcher-route-planner/1.0 (field service routing prototype)"

# Nominatim просит не чаще одного запроса в секунду; у Яндекса лимит мягче.
RATE_LIMIT_SEC = {"nominatim": 1.1, "yandex": 0.25}

RAW_DIR = os.path.join(ROOT, "data", "raw")
CACHE_PATH = os.path.join(ROOT, "data", "geo_cache.json")


def collect_addresses() -> list[tuple[str, str, str]]:
    """Уникальные (ключ, исходный адрес, район) из всех выгрузок."""
    seen: dict[str, tuple[str, str, str]] = {}
    for key in REGIONS:
        path = os.path.join(RAW_DIR, f"{key}_control.csv")
        if not os.path.exists(path):
            continue
        with open(path, "rb") as fh:
            text = fh.read().decode(RAW_ENCODING)
        for row in csv.DictReader(io.StringIO(text), delimiter=CSV_DELIMITER):
            if not (row.get("Заявка") or "").strip():
                continue
            address = _clean_address(row.get("Адрес", ""))
            district = row.get("Район", "").strip()
            k = normalize_address(address)
            if k and k not in seen:
                seen[k] = (k, address, district)
    return list(seen.values())


GENERIC = "улица|проспект|переулок|бульвар|набережная|проезд|шоссе|площадь"


def build_query(address: str, district: str) -> str:
    """Готовит строку запроса: чистит сокращения, добавляет город."""
    addr = address
    addr = re.sub(r",\s*кв\.?\s*\d+.*$", "", addr, flags=re.I)

    # Подмосковные адреса приходят в своей форме: «МО, г. Кашира Центральная
    # улица 21», «обл.Московская область, г.Домодедово, пгт.Востряково-1, …».
    # Геокодер видит это одной строкой и не находит ничего, поэтому сначала
    # приводим к обычному «Город, улица, дом».
    addr = re.sub(r"^\s*(?:обл\.?\s*)?Московская\s+область\s*,?\s*", "", addr, flags=re.I)
    # \b обязателен: без него «МО» без учёта регистра съедает «Мо» в «Москва».
    addr = re.sub(r"^\s*МО\b\s*,?\s*", "", addr)
    addr = re.sub(r"\bпгт\.?\s*", "", addr, flags=re.I)
    addr = re.sub(r"\bг\.\s*([А-ЯЁ][а-яё\-]+)\s*,?", r"\1, ", addr)

    addr = addr.replace("пр-кт.", "проспект ").replace("ул.", "улица ")
    addr = addr.replace("пер.", "переулок ").replace("б-р.", "бульвар ")
    addr = addr.replace("наб.", "набережная ").replace("проезд.", "проезд ")
    addr = addr.replace("пр-зд.", "проезд ").replace("пр-д.", "проезд ")
    addr = addr.replace("ш.", "шоссе ").replace("пл.", "площадь ")
    addr = re.sub(r"\bд\.\s*", "", addr)
    addr = re.sub(r"\s*к\s*(\d+)", r" к\1", addr)
    addr = re.sub(r"\s+", " ", addr).strip(" ,")

    # Запятых может не быть вовсе: «Москва Булатниковский проезд 6 к1».
    # Отделяем город и номер дома, иначе запрос не разбирается на части.
    addr = re.sub(r"^(Москва)\s+(?=[А-ЯЁ])", r"\1, ", addr)
    addr = re.sub(rf"({GENERIC})\s+(\d[^,]*)$", r"\1, \2", addr, flags=re.I)

    city = normalize_district(district)
    if ("Москва" not in addr and city not in addr
            and city in {"Домодедово", "Кашира", "Ступино"}):
        addr = f"{city}, {addr}"
    return addr


# Что геокодеры знают хуже всего: строение, корпус, литера при номере дома.
_STROENIE = re.compile(r"\s*(?:стр\.?|строение|влд\.?|владение)\s*\d+\w*", re.I)
_KORPUS = re.compile(r"\s*к\s*\d+\w*$", re.I)
_LITERA = re.compile(r"^(\d+)\s*[а-яёa-z]$", re.I)
_ORDINAL = re.compile(rf"^((?:.*,\s*)?)({GENERIC})\s+(\d+-[а-яё]{{1,2}}\s+.+)$", re.I)


def reorder_ordinal(street: str) -> str | None:
    """«улица 3-я Институтская» -> «3-я Институтская улица».

    В русских названиях с порядковым номером родовое слово стоит после имени,
    но в выгрузке сокращение «ул.» всегда идёт первым. Развёрнутое «улица 3-я
    Институтская» геокодеру знакомо хуже, поэтому пробуем и обычный порядок.
    """
    match = _ORDINAL.match(street)
    if not match:
        return None
    return f"{match.group(1)}{match.group(3)} {match.group(2).lower()}"


def fallback_queries(query: str) -> list[str]:
    """Более грубые варианты запроса, если точный адрес не нашёлся.

    Ни Nominatim, ни Яндекс не всегда знают корпус, строение и литеру, но
    улицу и основной номер дома знают почти всегда. Точка на нужной улице
    честнее центра района: ошибка в сотни метров вместо километров.

    Варианты идут от точного к грубому, дубликаты выброшены.
    """
    street, sep, house = query.rpartition(",")
    street, house = street.strip(), house.strip()
    if not sep or not house[:1].isdigit():
        alt = reorder_ordinal(query)
        return [alt] if alt else []

    out: list[str] = []

    def add(name: str, value: str) -> None:
        candidate = f"{name}, {value}" if value else name
        if candidate != query and candidate not in out:
            out.append(candidate)

    streets = [street]
    alt = reorder_ordinal(street)
    if alt:
        streets.append(alt)
        add(alt, house)                     # тот же дом, другой порядок слов

    for name in streets:
        current = house
        for pattern in (_STROENIE, _KORPUS):
            trimmed = pattern.sub("", current).strip(" ,")
            if trimmed and trimmed != current:
                current = trimmed
                add(name, current)
        litera = _LITERA.match(current)
        if litera:
            current = litera.group(1)
            add(name, current)
        if "/" in current:                  # «24/30» — номер по двум улицам
            add(name, current.split("/")[0].strip())
        add(name, "")                       # последняя попытка: одна улица
    return out


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
    """HTTP Геокодер Яндекса. Координаты приходят строкой «долгота широта»."""
    params = urllib.parse.urlencode({
        "apikey": api_key, "geocode": query, "format": "json",
        "results": 1, "lang": "ru_RU",
    })
    data = _request(f"{YANDEX_GEOCODER}?{params}")
    if not data:
        return None
    try:
        members = data["response"]["GeoObjectCollection"]["featureMember"]
        if not members:
            return None
        lon, lat = members[0]["GeoObject"]["Point"]["pos"].split()
        return float(lat), float(lon)
    except (KeyError, IndexError, ValueError) as exc:
        print(f"    ! неожиданный ответ геокодера: {exc}")
        return None


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
        print("Для Яндекс Геокодера нужен ключ YANDEX_GEOCODER_API_KEY — "
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
    print(f"Кэш: {CACHE_PATH} — закоммитьте его в репозиторий.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
