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

_MEASURE = r"""
() => {
  const problems = [];
  const doc = document.documentElement;
  if (doc.scrollWidth > doc.clientWidth + 1) {
    problems.push({kind: 'page-scroll', detail: `${doc.scrollWidth} > ${doc.clientWidth}`});
  }
  // Карту из замера исключаем целиком: она рисует подписи и метки
  // абсолютным позиционированием, и каждая из них читается как наложение.
  const map = document.querySelector('[data-testid="map"]');

  // При открытом модальном окне меряем только его. Страница под затемнением
  // никуда не девается, и каждый её элемент читается как наложение: замер
  // упирается в предел находок, не сказав ничего о самом окне.
  // Верхний слой меряется отдельно: страница под ним никуда не девается, и
  // каждый её элемент читается как наложение. Карточка заявки лежит поверх
  // содержимого так же, как модальное окно.
  const top = document.querySelector('[role="dialog"]')
    || document.querySelector('[data-testid="detail"]');
  const root = top || document.body;

  // Ближайший предок, который обрезает содержимое: по нему видно, что
  // человек на экране действительно видит.
  function clipped(el, box) {
    // Содержимое свёрнутого <details> браузер не рисует, но координаты у
    // него есть: все абзацы ложатся в одну точку и читаются как наложения.
    if (el.closest('details:not([open])')) return true;
    for (let node = el.parentElement; node && node !== root; node = node.parentElement) {
      const how = getComputedStyle(node);
      if (how.overflowY === 'visible' && how.overflowX === 'visible') continue;
      const edge = node.getBoundingClientRect();
      if (box.bottom > edge.bottom + 1 || box.top < edge.top - 1) return true;
      if (box.right > edge.right + 1 || box.left < edge.left - 1) return true;
    }
    return false;
  }


  // --- читаемость и доступность -------------------------------------------
  // Геометрия ловит только сдвиги. Всё остальное - контраст, размер целей,
  // безымянные кнопки, текст, срезанный вместе с контейнером - до сих пор
  // держалось на чужих глазах, и каждый круг ревью находил это заново.

  function channel(v) {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  }

  function luminance(rgb) {
    return 0.2126 * channel(rgb[0]) + 0.7152 * channel(rgb[1]) + 0.0722 * channel(rgb[2]);
  }

  function parseColor(value) {
    const m = value.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const parts = m[1].split(/[,\s\/]+/).filter(Boolean).map(Number);
    if (parts.length < 3 || parts.some(Number.isNaN)) return null;
    return {rgb: parts.slice(0, 3), alpha: parts.length > 3 ? parts[3] : 1};
  }

  // Фон элемента: первый непрозрачный предок. Полупрозрачные слои смешиваем
  // с тем, что под ними, иначе подложка bg-raised/50 даёт неверный расчёт.
  function backdrop(el) {
    let rgb = [255, 255, 255];
    const stack = [];
    for (let node = el; node; node = node.parentElement) {
      const how = getComputedStyle(node);
      if (how.backgroundImage && how.backgroundImage !== 'none') return null;
      const color = parseColor(how.backgroundColor);
      if (!color || color.alpha === 0) continue;
      stack.push(color);
      if (color.alpha === 1) { rgb = color.rgb; break; }
    }
    for (let i = stack.length - 1; i >= 0; i--) {
      const layer = stack[i];
      if (layer.alpha === 1) { rgb = layer.rgb; continue; }
      rgb = rgb.map((base, k) => base * (1 - layer.alpha) + layer.rgb[k] * layer.alpha);
    }
    return rgb;
  }

  function ratio(a, b) {
    const la = luminance(a), lb = luminance(b);
    return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
  }

  const boxes = [];
  for (const el of root.querySelectorAll('*')) {
    if (map && map.contains(el)) continue;
    const style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') continue;
    const box = el.getBoundingClientRect();
    if (box.width === 0 || box.height === 0) continue;

    // Содержимое шире собственного контейнера: строка меток шире карточки,
    // номер за краем. Прокрутки страницы при этом может не быть вовсе.
    const parent = el.parentElement;
    if (parent && style.position !== 'absolute' && style.position !== 'fixed') {
      const outer = parent.getBoundingClientRect();
      const room = getComputedStyle(parent).overflowX;
      const scrolls = room === 'auto' || room === 'scroll' || room === 'hidden';
      if (!scrolls && box.right > outer.right + 1) {
        problems.push({kind: 'overflow', tag: el.tagName.toLowerCase(),
          cls: el.className.toString().slice(0, 40),
          detail: Math.round(box.right - outer.right) + 'px за контейнер'});
      }
    }
    const text = (el.textContent || '').trim();

    // --- контраст текста ---
    if (text && el.children.length === 0 && !clipped(el, box)) {
      const ink = parseColor(style.color);
      const paper = backdrop(el);
      if (ink && paper && ink.alpha > 0.85) {
        const size = parseFloat(style.fontSize);
        const heavy = Number(style.fontWeight) >= 700;
        // Порог WCAG AA: крупному тексту хватает 3.0, остальному нужно 4.5.
        const need = (size >= 24 || (size >= 18.66 && heavy)) ? 3.0 : 4.5;
        const got = ratio(ink.rgb, paper);
        if (got < need) {
          problems.push({kind: 'contrast',
            detail: `«${text.slice(0, 24)}» ${got.toFixed(1)}:1 при нужных ${need}`});
        }
      }
    }

    // --- размер цели нажатия ---
    const clickable = el.matches('button, a[href], input, select, [role="button"], [role="tab"]');
    if (clickable && !clipped(el, box) && style.display !== 'contents') {
      // Поле внутри метки - одна цель с ней: клик по метке попадает в поле.
      const owner = el.closest('label') || el;
      const reach = owner.getBoundingClientRect();
      const side = Math.min(Math.max(box.width, reach.width),
                            Math.max(box.height, reach.height));
      // Порог WCAG 2.2: цель меньше 24 px не берётся пальцем и плохо берётся
      // мышью. Скрытые поля выбора файла не считаем.
      if (side < 24 && style.opacity !== '0') {
        problems.push({kind: 'target',
          detail: `«${(el.getAttribute('aria-label') || text || el.tagName).slice(0, 24)}»`
            + ` ${Math.round(box.width)}x${Math.round(box.height)}`});
      }
    }

    // --- кнопка без имени ---
    if (el.matches('button, a[href], [role="button"]') && !clipped(el, box)) {
      const named = text || el.getAttribute('aria-label') || el.getAttribute('title')
        || el.querySelector('[aria-label], title, svg title');
      if (!named) {
        problems.push({kind: 'nameless',
          detail: `${el.tagName.toLowerCase()}.${el.className.toString().slice(0, 30)}`});
      }
    }

    // --- текст, срезанный контейнером без многоточия ---
    if (text && el.children.length === 0) {
      const room = getComputedStyle(el);
      const hides = room.overflowX === 'hidden' || room.overflowY === 'hidden';
      const ellipsis = room.textOverflow === 'ellipsis';
      if (hides && !ellipsis
          && (el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1)) {
        problems.push({kind: 'cut', detail: `«${text.slice(0, 24)}» не помещается и обрезан`});
      }
    }

    // Элемент, уехавший за край своего прокручиваемого контейнера, на экране
    // обрезан. Сравнивать его с видимыми соседями значит находить наложения
    // там, где человек видит аккуратный список.
    if (text && el.children.length === 0 && !clipped(el, box)) {
      boxes.push({box, text: text.slice(0, 30)});
    }
  }

  // Наложение текста на текст: соседи по разметке, залезшие друг на друга.
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i].box, b = boxes[j].box;
      const wide = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const tall = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      if (wide > 4 && tall > 4) {
        problems.push({kind: 'overlap', detail: `«${boxes[i].text}» и «${boxes[j].text}»`});
      }
    }
  }
  return {
    problems: problems.slice(0, 25),
    // Строки таблицы считаются наравне с карточками: без них полное окно
    // со сводной таблицей отчитывается как пустое.
    content: root.querySelectorAll(
      'table tr, td, th, li, dt, dd, p, h1, h2, h3, h4, button,'
      + ' [data-testid^="metric"]').length,
  };
}
"""


#: Адреса внешней карты. При съёмке они отклоняются сразу: недоступная карта
#: отваливается по таймауту соединения и держит интерфейс десятками секунд, а
#: результат съёмки начинает зависеть от сети.
MAP_HOSTS = ("**api-maps.yandex.ru**", "**yandex.ru/maps**", "**yastatic.net**")


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
