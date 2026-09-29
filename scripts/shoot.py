"""Съёмка экрана диспетчера и замер вёрстки.

Агент не видит того, что пишет. Снимок показывает экран, а замер - то, чего не
видно и на снимке: текст, вылезший за свой контейнер, наложение блоков и
пустоту, которая выглядит как готовый экран.

Запуск: python scripts/shoot.py --state planned [--url ...] [--out reports/shots]
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import TypedDict

from playwright.async_api import Page, async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeout
from shoot_events import EVENT_STATES
from shoot_states import STATES as BASE_STATES

STATES = {**BASE_STATES, **EVENT_STATES}


class Measured(TypedDict):
    """Что вернул замер страницы."""

    problems: list[dict[str, str]]
    content: int
    # Сценарий довёл экран до нужного вида. Если нет, замер говорит о чужом
    # экране: снятое меню вместо окна отчитывалось как «чисто».
    reached: bool


#: Обязательные ширины. 390 - телефон, он входит в прогон всегда: заказчик
#: назвал адаптивность витрины под телефон фактором преимуществ (созвон
#: 37:21), а экран, который на ней разваливается, готовым не считается.
WIDTHS = (1440, 1024, 768, 390)

#: Сколько содержимого должно быть на экране, чтобы проверки что-то значили.
#: На пустой странице нарушений ноль, и гейт пишет «пройдено», ничего не
#: проверив.
MIN_CONTENT = 3

#: Замер вёрстки исполняется в браузере; текст скрипта лежит рядом.
_MEASURE = (Path(__file__).parent / "shoot_measure.js").read_text(encoding="utf-8")


#: Адреса внешней карты. При съёмке они отклоняются сразу: недоступная карта
#: отваливается по таймауту соединения и держит интерфейс десятками секунд, а
#: результат съёмки начинает зависеть от сети.
MAP_HOSTS = ("**api-maps.yandex.ru**", "**yandex.ru/maps**", "**yastatic.net**",
             "**tile.openstreetmap.org**")


async def _block_map(page: Page) -> None:
    """Отклонять обращения к внешней карте, оставляя запасную схему."""
    for pattern in MAP_HOSTS:
        await page.route(pattern, lambda route: route.abort())


async def _shoot(page: Page, url: str, state: str, out: Path) -> dict[str, Measured]:
    """Снять состояние во всех ширинах и замерить каждую."""
    report: dict[str, Measured] = {}
    for width in WIDTHS:
        await page.set_viewport_size({"width": width, "height": 900})
        # Сценарий проигрывается заново на каждой ширине: интерфейс
        # одностраничный, и смена размера окна состояние не пересобирает.
        await page.goto(url, wait_until="domcontentloaded")
        reached = True
        try:
            await STATES[state](page)
        except PlaywrightTimeout as error:
            # Печатаем, чего именно не дождались: без этого непонятно, экран
            # не собрался или сценарий ждёт того, чего на нём не бывает.
            reached = False
            step = str(error).strip().splitlines()[0]
            print(f"{width}: состояние «{state}» НЕ СОБРАЛОСЬ: {step}")
        # Анимации доигрывают, карта дорисовывается.
        await page.wait_for_timeout(800)
        await page.screenshot(path=str(out / f"{state}-{width}.png"), full_page=True)
        found: Measured = await page.evaluate(_MEASURE)
        found["reached"] = reached
        report[str(width)] = found
    return report


def _print(state: str, report: dict[str, Measured]) -> None:
    """Напечатать находки по одному состоянию."""
    print(f"\n=== {state}")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    for width, found in report.items():
        counted = int(found["content"])
        problems = found["problems"]
        if not found.get("reached", True):
            print(f"{width}: состояние не собралось, снят чужой экран")
        elif counted < MIN_CONTENT:
            print(f"{width}: содержимого почти нет ({counted}), проверять нечего")
        elif problems:
            print(f"{width}: находок {len(problems)}")
        else:
            print(f"{width}: чисто, содержимого {counted}")


async def main() -> None:
    """Снять состояния экрана и напечатать находки."""
    # Вывод идёт в консоль Windows, а она по умолчанию не UTF-8: без этого
    # находки печатаются нечитаемыми и молча теряют смысл.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="shoot")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--out", default="reports/shots")
    parser.add_argument("--state", default="planned", choices=sorted(STATES))
    parser.add_argument("--all", action="store_true", help="снять все состояния")
    parser.add_argument("--live-map", action="store_true",
                        help="не отклонять внешнюю карту: снять её настоящей")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    states = sorted(STATES) if args.all else [args.state]

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="chrome")
        page = await browser.new_page()
        if not args.live_map:
            await _block_map(page)
        failed: list[str] = []
        for state in states:
            report = await _shoot(page, args.url, state, out)
            _print(state, report)
            if any(not found.get("reached", True) for found in report.values()):
                failed.append(state)
        await browser.close()

    if failed:
        # Несобравшееся состояние это провал проверки, а не мелочь: съёмка
        # чужого экрана выдаёт себя за доказательство исправления.
        print()
        print(f"НЕ СОБРАЛИСЬ: {', '.join(failed)}")
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
