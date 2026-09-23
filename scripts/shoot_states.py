"""Сценарии состояний экрана диспетчера.

Состояние достигается действиями, а не адресом: интерфейс одностраничный, и
план появляется только после нажатия. Каждая функция доводит страницу до
нужного вида и возвращается, когда вид готов.
"""
from collections.abc import Awaitable, Callable

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeout
from shoot_steps import (
    PLAN_TIMEOUT_MS,
    SHORTFALL_REGION,
    UNPLANNED_REGION,
    open_check,
    open_menu,
    plan_day,
    ready,
)


async def first_run(page: Page) -> None:
    """Первый вход: участок не выбран, расчёт не начат."""
    await ready(page)


async def not_planned(page: Page) -> None:
    """Участок выбран, план ещё не построен.

    Подходит только участок без плана. Перебираем все и берём первый чистый:
    жёстко заданный участок ломался, стоило посчитать его руками. Сводки на
    экране при этом быть не должно - заголовок «ещё не построен»
    показывается и во время расчёта.

    День переживает перезапуск сервиса (версии лежат в базе), поэтому
    перезапуском это состояние больше не вернуть: нужен `clear_day.py`.
    """
    await ready(page)
    options = await page.eval_on_selector_all(
        'select[aria-label="Участок"] option[value]:not([value=""])',
        "nodes => nodes.map(node => node.value)")

    for region in [UNPLANNED_REGION, *options]:
        if region not in options:
            continue
        await page.select_option('select[aria-label="Участок"]', region)
        try:
            await page.wait_for_selector("text=План на сегодня ещё не построен",
                                         timeout=5_000)
            await page.wait_for_selector('[data-testid="metric-assigned"]',
                                         state="detached", timeout=5_000)
        except PlaywrightTimeout:
            continue
        return

    raise PlaywrightTimeout(
        "ни один участок не подошёл: планы построены на всех. Сверните дни "
        "перед съёмкой: python scripts/clear_day.py")


async def planned(page: Page) -> None:
    """План построен: сводка, маршруты, карта."""
    await plan_day(page)


async def route_open(page: Page) -> None:
    """Маршрут раскрыт до остановок с оборудованием."""
    await plan_day(page)
    await page.click('[data-testid="work-list"] li button >> nth=0')
    await page.wait_for_selector('[data-testid="work-list"] ul ul li')


async def unassigned(page: Page) -> None:
    """Заявки без исполнителя с причинами словами."""
    await plan_day(page, SHORTFALL_REGION)
    await page.click('button[role="tab"]:has-text("Без исполнителя")')


async def detail(page: Page) -> None:
    """Карточка объяснения назначения поверх карты."""
    await route_open(page)
    await page.click('[data-testid="work-list"] ul ul li button >> nth=0')
    await page.wait_for_selector('[data-testid="detail"]', timeout=PLAN_TIMEOUT_MS)


async def event_form(page: Page) -> None:
    """Полоса события раскрыта, поля заполняются.

    Каждый шаг дожидается своего следствия: клик по свёрнутой полосе и клик
    по виду события идут подряд, и без ожидания второй попадает в ещё не
    отрисованную форму.
    """
    await plan_day(page)
    await page.click('button:has-text("Событие в течение дня")')
    kind = page.locator('button:has-text("Задержка бригады")')
    await kind.wait_for(state="visible", timeout=30_000)
    await kind.scroll_into_view_if_needed()
    await kind.click()
    await page.wait_for_selector('text=Задержка, мин', state="visible", timeout=30_000)


async def event_preview(page: Page) -> None:
    """Предпросмотр события: что станет, если применить."""
    await event_form(page)
    await page.select_option('select >> nth=1', index=1)
    await page.click('button:has-text("Посмотреть, что изменится")')
    await page.wait_for_selector('[data-testid="event-preview"]', timeout=PLAN_TIMEOUT_MS)


async def menu(page: Page) -> None:
    """Меню смены открыто."""
    await plan_day(page)
    await page.click('button:has-text("Меню")')
    await page.wait_for_selector('[data-testid="drawer"]')


async def compare(page: Page) -> None:
    """Сравнение способов расчёта."""
    await plan_day(page)
    await open_menu(page, "Сравнить способы расчёта")
    await page.wait_for_selector("text=Задача нетривиальна", timeout=PLAN_TIMEOUT_MS)


async def risk(page: Page) -> None:
    """Прогноз опозданий."""
    await plan_day(page)
    await open_check(page, "Опоздания", "Прогноз опозданий", "Прогноз опозданий")


async def validate(page: Page) -> None:
    """Независимая проверка плана."""
    await plan_day(page)
    await open_check(page, "Проверить план", "Проверить план", "Проверка плана")
    await page.wait_for_selector("text=/Нарушений нет|Найдены нарушения/",
                                 timeout=PLAN_TIMEOUT_MS)


async def pickup(page: Page) -> None:
    """Ведомость на выдачу оборудования."""
    await plan_day(page)
    await open_check(page, "Ведомость", "Что взять в офисе", "Что взять в офисе")


async def shortfall(page: Page) -> None:
    """Разбор нехватки бригад.

    Путь человека: строка в очереди решений, а не отдельная кнопка метрики.
    """
    await plan_day(page, SHORTFALL_REGION)
    await page.click('button:has-text("Нужно ещё")')
    await page.wait_for_selector('[role="dialog"]:has-text("Сколько ещё нужно бригад")',
                                 timeout=PLAN_TIMEOUT_MS)


async def assumptions(page: Page) -> None:
    """Карточка допущений: как считаем."""
    await plan_day(page)
    await open_menu(page, "Как считаем")


async def upload(page: Page) -> None:
    """Загрузка своего набора данных.

    Путь человека: кнопка прямо в пустом состоянии, а не через меню.
    """
    await ready(page)
    await page.click('button:has-text("Загрузить свой набор данных")')
    await page.wait_for_selector('[role="dialog"]:has-text("Загрузить свой набор данных")',
                                 timeout=PLAN_TIMEOUT_MS)


#: Состояния, которые снимаются в обычном прогоне. Порядок такой же, как в
#: скилле `dispatcher-ux-review`.
STATES: dict[str, Callable[[Page], Awaitable[None]]] = {
    "first-run": first_run,
    "not-planned": not_planned,
    "planned": planned,
    "route-open": route_open,
    "unassigned": unassigned,
    "detail": detail,
    "event-form": event_form,
    "event-preview": event_preview,
    "menu": menu,
    "compare": compare,
    "risk": risk,
    "validate": validate,
    "pickup": pickup,
    "shortfall": shortfall,
    "assumptions": assumptions,
    "upload": upload,
}
