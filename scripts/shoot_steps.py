"""Общие шаги сценариев съёмки: дождаться участков, план, меню, проверки."""
from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeout

#: Сколько ждать построение плана. Поиск останавливается по числу улучшений,
#: и на самом большом участке это до двух минут; под браузером и съёмкой
#: дольше. Запас втрое: упор в таймаут выглядит как несобравшееся состояние,
#: хотя сервис просто ещё считает.
PLAN_TIMEOUT_MS = 300_000

#: Сколько ждать первую отрисовку: список участков приходит от сервиса.
READY_TIMEOUT_MS = 60_000

REGION = "vostok"

#: Участок, который в прогоне не планируется: нужен состоянию «план ещё не
#: построен», иначе оно достижимо только первым снимком за запуск сервиса.
UNPLANNED_REGION = "yugo_vostok"

#: Участок, где после расчёта остаются заявки без исполнителя и нехватка
#: бригад: на Востоке разошлись все 66, и показывать там нечего.
SHORTFALL_REGION = "yugocentr"


async def ready(page: Page) -> None:
    """Дождаться, пока страница получит список участков."""
    # Ждём появления в разметке, а не видимости: пункт закрытого списка
    # невидим по определению, и проверка на видимость висит до таймаута.
    await page.wait_for_selector(
        'select[aria-label="Участок"] option[value="vostok"]',
        state="attached", timeout=READY_TIMEOUT_MS)


async def plan_day(page: Page, region: str = REGION) -> None:
    """Довести экран до готового плана.

    Сервис держит посчитанный день в памяти, и открытая заново страница
    показывает его сразу. Пересчитывать ради каждого состояния незачем:
    расчёт занимает до двух минут, а диспетчер утром тоже строит план один
    раз и дальше работает с ним.
    """
    await ready(page)
    await page.select_option('select[aria-label="Участок"]', region)

    shown = page.locator('[data-testid="metric-assigned"]')
    try:
        await shown.wait_for(state="visible", timeout=5_000)
    except PlaywrightTimeout:
        pass
    else:
        await page.wait_for_selector('[data-testid="work-list"]', timeout=30_000)
        return

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


async def open_menu(page: Page, title: str) -> None:
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


async def open_check(page: Page, button: str, menu_title: str, window: str) -> None:
    """Открыть проверку дня.

    На широком экране проверки стоят кнопками в сводке, на узком уезжают в
    меню: сценарий идёт тем же путём, что и человек.
    """
    top = page.locator(f'[data-testid="day-checks"] button:has-text("{button}")').first
    if await top.count() and await top.is_visible():
        await top.click()
    else:
        await open_menu(page, menu_title)
    await page.wait_for_selector(f'[role="dialog"]:has-text("{window}")',
                                 timeout=PLAN_TIMEOUT_MS)
