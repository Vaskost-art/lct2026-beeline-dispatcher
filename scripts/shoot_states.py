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

#: Участок, который в прогоне не планируется: нужен состоянию «план ещё не
#: построен», иначе оно достижимо только первым снимком за запуск сервиса.
UNPLANNED_REGION = "yugocentr"


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
    # Сначала дожидаемся, что расчёт действительно начался: иначе условие
    # «кнопка снова доступна» совпадает мгновенно, и снимок застаёт экран
    # посреди счёта, с вечной надписью «Считаем».
    await page.wait_for_selector('[data-testid="plan"][disabled]', timeout=30_000)
    # Признак окончания - кнопка расчёта снова доступна. Ждать появления
    # чисел нельзя: на экране остаются прежние, пока считается новый план.
    await page.wait_for_selector('[data-testid="plan"]:not([disabled])',
                                 timeout=PLAN_TIMEOUT_MS)
    await page.wait_for_selector('[data-testid="work-list"]', timeout=PLAN_TIMEOUT_MS)


async def _menu(page: Page, title: str) -> None:
    """Открыть пункт меню и дождаться его окна.

    Пункт ищется внутри самой шторки: те же слова встречаются и на экране
    (кнопка пустого состояния, кнопка проверки), и выбор «любой кнопки с
    таким текстом» отказывает.
    """
    await page.click('button:has-text("Меню")')
    await page.click(f'[data-testid="drawer"] button:has-text("{title}")')
    # Ждём, пока шторка уйдёт. Ищем её по метке, а не по словам: заголовок
    # окна не повторяет название пункта («Проверить план» открывает
    # «Проверку плана»), а слово «Смена» встречается и в карточке допущений.
    await page.wait_for_selector('[data-testid="drawer"]',
                                 state="detached", timeout=30_000)


async def _check(page: Page, button: str, menu_title: str, window: str) -> None:
    """Открыть проверку дня.

    На широком экране проверки стоят кнопками в сводке, на узком уезжают в
    меню: сценарий идёт тем же путём, что и человек.
    """
    top = page.locator(f'[data-testid="day-checks"] button:has-text("{button}")').first
    if await top.count() and await top.is_visible():
        await top.click()
    else:
        await _menu(page, menu_title)
    await page.wait_for_selector(f'[role="dialog"]:has-text("{window}")',
                                 timeout=PLAN_TIMEOUT_MS)


async def first_run(page: Page) -> None:
    """Первый вход: участок не выбран, расчёт не начат."""
    await _ready(page)


async def not_planned(page: Page) -> None:
    """Участок выбран, план ещё не построен.

    Берём участок, который в прогоне никто не планирует: сервис держит
    построенный план в памяти, и на рабочем участке это состояние живёт
    ровно до первой съёмки. Дополнительно убеждаемся, что сводки на экране
    нет: заголовок появляется и во время расчёта.
    """
    await _ready(page)
    await page.select_option('select[aria-label="Участок"]', UNPLANNED_REGION)
    await page.wait_for_selector("text=План на сегодня ещё не построен")
    await page.wait_for_selector('[data-testid="metric-assigned"]', state="detached")


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
    """Полоса события раскрыта, поля заполняются.

    Каждый шаг дожидается своего следствия: клик по свёрнутой полосе и клик
    по виду события идут подряд, и без ожидания второй попадает в ещё не
    отрисованную форму.
    """
    await _plan(page)
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
    await _plan(page)
    await page.click('button:has-text("Меню")')
    await page.wait_for_selector('[data-testid="drawer"]')


async def compare(page: Page) -> None:
    """Сравнение способов расчёта."""
    await _plan(page)
    await _menu(page, "Сравнить способы расчёта")
    await page.wait_for_selector("text=Задача нетривиальна", timeout=PLAN_TIMEOUT_MS)


async def risk(page: Page) -> None:
    """Прогноз опозданий."""
    await _plan(page)
    await _check(page, "Опоздания", "Прогноз опозданий", "Прогноз опозданий")


async def validate(page: Page) -> None:
    """Независимая проверка плана."""
    await _plan(page)
    await _check(page, "Проверить план", "Проверить план", "Проверка плана")
    await page.wait_for_selector("text=/Нарушений нет|Найдены нарушения/",
                                 timeout=PLAN_TIMEOUT_MS)


async def pickup(page: Page) -> None:
    """Ведомость на выдачу оборудования."""
    await _plan(page)
    await _check(page, "Ведомость", "Что взять в офисе", "Что взять в офисе")


async def shortfall(page: Page) -> None:
    """Разбор нехватки бригад.

    Путь человека: строка в очереди решений, а не отдельная кнопка метрики.
    """
    await _plan(page)
    await page.click('button:has-text("Нужно ещё")')
    await page.wait_for_selector('[role="dialog"]:has-text("Сколько ещё нужно бригад")',
                                 timeout=PLAN_TIMEOUT_MS)


async def assumptions(page: Page) -> None:
    """Карточка допущений: как считаем."""
    await _plan(page)
    await _menu(page, "Как считаем")


async def upload(page: Page) -> None:
    """Загрузка своего набора данных.

    Путь человека: кнопка прямо в пустом состоянии, а не через меню.
    """
    await _ready(page)
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
