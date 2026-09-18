"""Сценарии состояний экрана диспетчера.

Состояние достигается действиями, а не адресом: интерфейс одностраничный, и
план появляется только после нажатия. Каждая функция доводит страницу до
нужного вида и возвращается, когда вид готов.
"""
from collections.abc import Awaitable, Callable

from playwright.async_api import Page

#: Сколько ждать построение плана. Расчёт ограничен временем на стороне
#: сервиса, но геокодирование и отрисовка карты добавляют сверху.
PLAN_TIMEOUT_MS = 120_000

#: Сколько ждать первую отрисовку: список участков приходит от сервиса.
READY_TIMEOUT_MS = 60_000

REGION = "vostok"


async def _ready(page: Page) -> None:
    """Дождаться, пока страница получит список участков."""
    # Ждём появления в разметке, а не видимости: пункт закрытого списка
    # невидим по определению, и проверка на видимость висит до таймаута.
    await page.wait_for_selector(
        'select[aria-label="Участок"] option[value="vostok"]',
        state="attached", timeout=READY_TIMEOUT_MS)


async def _plan(page: Page) -> None:
    """Выбрать участок, построить план и дождаться конца расчёта."""
    await _ready(page)
    await page.select_option('select[aria-label="Участок"]', REGION)
    await page.click('[data-testid="plan"]')
    # Признак окончания - кнопка расчёта снова доступна. Ждать появления
    # чисел нельзя: на экране остаются прежние, пока считается новый план.
    await page.wait_for_selector('[data-testid="plan"]:not([disabled])',
                                 timeout=PLAN_TIMEOUT_MS)
    await page.wait_for_selector('[data-testid="work-list"]', timeout=PLAN_TIMEOUT_MS)


async def _menu(page: Page, title: str) -> None:
    """Открыть пункт меню и дождаться его окна."""
    await page.click('button:has-text("Меню")')
    await page.click(f'button:has-text("{title}")')
    await page.wait_for_selector('[role="dialog"]', timeout=PLAN_TIMEOUT_MS)


async def first_run(page: Page) -> None:
    """Первый вход: участок не выбран, расчёт не начат."""
    await _ready(page)


async def not_planned(page: Page) -> None:
    """Участок выбран, план ещё не построен."""
    await _ready(page)
    await page.select_option('select[aria-label="Участок"]', REGION)
    await page.wait_for_selector("text=План на сегодня ещё не построен")


async def planned(page: Page) -> None:
    """План построен: сводка, маршруты, карта."""
    await _plan(page)


async def route_open(page: Page) -> None:
    """Маршрут раскрыт до остановок с оборудованием."""
    await _plan(page)
    await page.click('[data-testid="work-list"] li button >> nth=0')
    await page.wait_for_selector('[data-testid="work-list"] ul ul li')


async def unassigned(page: Page) -> None:
    """Заявки без исполнителя с причинами словами."""
    await _plan(page)
    await page.click('button[role="tab"]:has-text("Без исполнителя")')


async def detail(page: Page) -> None:
    """Карточка объяснения назначения поверх карты."""
    await route_open(page)
    await page.click('[data-testid="work-list"] ul ul li button >> nth=0')
    await page.wait_for_selector('[data-testid="detail"]', timeout=PLAN_TIMEOUT_MS)


async def event_form(page: Page) -> None:
    """Полоса события раскрыта, поля заполняются."""
    await _plan(page)
    await page.click('button:has-text("Событие в течение дня")')
    await page.click('button:has-text("Задержка бригады")')


async def event_preview(page: Page) -> None:
    """Предпросмотр события: что станет, если применить."""
    await event_form(page)
    await page.select_option('select >> nth=1', index=1)
    await page.click('button:has-text("Посмотреть, что изменится")')
    await page.wait_for_selector('[data-testid="event-preview"]', timeout=PLAN_TIMEOUT_MS)


async def menu(page: Page) -> None:
    """Меню смены открыто."""
    await _plan(page)
    await page.click('button:has-text("Меню")')
    await page.wait_for_selector('[role="dialog"]:has-text("Смена")')


async def compare(page: Page) -> None:
    """Сравнение способов расчёта."""
    await _plan(page)
    await _menu(page, "Сравнить способы расчёта")
    await page.wait_for_selector("text=Задача нетривиальна", timeout=PLAN_TIMEOUT_MS)


async def risk(page: Page) -> None:
    """Прогноз опозданий."""
    await _plan(page)
    await _menu(page, "Прогноз опозданий")


async def validate(page: Page) -> None:
    """Независимая проверка плана."""
    await _plan(page)
    await _menu(page, "Проверить план")
    await page.wait_for_selector("text=/Нарушений нет|Найдены нарушения/",
                                 timeout=PLAN_TIMEOUT_MS)


async def pickup(page: Page) -> None:
    """Ведомость на выдачу оборудования."""
    await _plan(page)
    await _menu(page, "Что взять в офисе")


async def shortfall(page: Page) -> None:
    """Разбор нехватки бригад."""
    await _plan(page)
    await page.click('[data-testid="metric-shortfall"]')
    await page.wait_for_selector('[role="dialog"]:has-text("Сколько ещё нужно бригад")')


async def assumptions(page: Page) -> None:
    """Карточка допущений: как считаем."""
    await _plan(page)
    await _menu(page, "Как считаем")


async def upload(page: Page) -> None:
    """Загрузка своего набора данных."""
    await _ready(page)
    await page.click('button:has-text("Меню")')
    await page.click('button:has-text("Загрузить свой набор")')
    await page.wait_for_selector('[role="dialog"]:has-text("Загрузить свой набор")')


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
