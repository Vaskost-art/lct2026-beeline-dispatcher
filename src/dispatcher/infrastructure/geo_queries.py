"""Какими запросами искать адрес выгрузки у геокодера.

Адрес в выгрузке записан по-разному: с корпусом, строением, литерой, номером
по двум улицам. Первый запрос берёт адрес как есть, запасные постепенно его
упрощают, вплоть до одной улицы.
"""
from __future__ import annotations

import re

from dispatcher.domain.distance import normalize_district

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
    # Корпус стоит после номера дома: без цифры слева правило съедало «к» из
    # «переулок 1-й» и отдавало геокодеру «переуло к1-й».
    addr = re.sub(r"(\d)\s*к\s*(\d+)", r"\1 к\2", addr)
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
        if "/" in current:                  # «24/30» - номер по двум улицам
            add(name, current.split("/")[0].strip())
        add(name, "")                       # последняя попытка: одна улица
    return out
