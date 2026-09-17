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

#: Во сколько секунд укладывать расчёт при съёмке. Меньше значения по
#: умолчанию: нам нужен вид экрана, а не лучший маршрут.
SHOOT_TIME_LIMIT = "5"


#: Сколько ждать первую отрисовку. Интерфейс заполняет список районов только
#: после того, как отработает загрузка карты, а недоступная внешняя карта
#: отваливается по таймауту соединения, и это десятки секунд.
READY_TIMEOUT_MS = 120_000


async def _ready(page: Page) -> None:
    """Дождаться, пока страница получит список районов с сервиса."""
    # Ждём появления в разметке, а не видимости: пункт закрытого списка
    # невидим по определению, и проверка на видимость висит до таймаута.
    await page.wait_for_selector(
        "#region option", state="attached", timeout=READY_TIMEOUT_MS)


async def _settled(page: Page) -> None:
    """Дождаться конца расчёта.

    Метрики на экране остаются от прошлого плана, пока считается новый:
    съёмка по их появлению снимает старые числа поверх идущего расчёта.
    Признак окончания - кнопка расчёта снова доступна.
    """
    await page.wait_for_selector("#btnPlan:not([disabled])", timeout=PLAN_TIMEOUT_MS)
    await page.wait_for_selector("#metrics:not([hidden]) .metric", timeout=PLAN_TIMEOUT_MS)


async def _plan(page: Page) -> None:
    """Построить план и дождаться конца расчёта."""
    await _ready(page)
    # Интерфейс сам считает план при запуске. Дожидаемся его, иначе наш
    # расчёт встанет вторым и съёмка застанет экран в промежуточном виде.
    await _settled(page)
    await page.fill("#timeLimit", SHOOT_TIME_LIMIT)
    await page.click("#btnPlan")
    await page.wait_for_selector("#btnPlan[disabled]", timeout=30_000)
    await _settled(page)


async def _tab(page: Page, name: str) -> None:
    """Переключиться на вкладку левой панели."""
    await page.click(f'.tab[data-tab="{name}"]')
    await page.wait_for_selector(f"#tab-{name}:not([hidden])", timeout=10_000)


async def _modal(page: Page, button: str) -> None:
    """Нажать кнопку и дождаться открытого модального окна."""
    await page.click(button)
    await page.wait_for_selector("#modal:not([hidden]) #modalBody *", timeout=PLAN_TIMEOUT_MS)


async def empty(page: Page) -> None:
    """День не загружен: приглашение выбрать район."""
    await _ready(page)


async def planned(page: Page) -> None:
    """План построен: маршруты, метрики, карта."""
    await _plan(page)
    await _tab(page, "routes")


async def unassigned(page: Page) -> None:
    """Нераспределённые заявки и причины отказа."""
    await _plan(page)
    await _tab(page, "unassigned")


async def assumptions(page: Page) -> None:
    """Карточки допущений и нормативов."""
    await _plan(page)
    await _tab(page, "assumptions")


async def detail(page: Page) -> None:
    """Объяснение назначения в правой панели."""
    await _plan(page)
    await _tab(page, "routes")
    await page.click(".route .route-head")
    await page.wait_for_selector(".route.open .stop", timeout=10_000)
    await page.click(".route.open .stop")
    await page.wait_for_selector("#detail .detail-section", timeout=PLAN_TIMEOUT_MS)


async def compare(page: Page) -> None:
    """Сравнение вариантов плана."""
    await _plan(page)
    await _modal(page, "#btnCompare")


async def risk(page: Page) -> None:
    """Прогноз опозданий."""
    await _plan(page)
    await _modal(page, "#btnRisk")


async def validate(page: Page) -> None:
    """Результат проверки ограничений."""
    await _plan(page)
    await _modal(page, "#btnValidate")


async def replan_engineer(page: Page) -> None:
    """День переигран после того, как бригада выбыла."""
    await _plan(page)
    await page.click("#replanBar .replan-head")
    await page.select_option("#eventKind", index=0)
    await page.wait_for_timeout(200)
    # Тип события задаёт, какие поля видны. Берём тот, при котором появляется
    # выбор исполнителя: именно он переигрывает уже выполненную часть дня.
    kinds = await page.eval_on_selector_all(
        "#eventKind option", "opts => opts.map(o => o.value)")
    for kind in kinds:
        await page.select_option("#eventKind", kind)
        await page.wait_for_timeout(150)
        if await page.is_visible("#fieldEngineer"):
            break
    await page.click("#btnReplan")
    await _settled(page)


async def urgent(page: Page) -> None:
    """Форма срочной заявки с выбором точки на карте."""
    await _plan(page)
    await page.click("#replanBar .replan-head")
    kinds = await page.eval_on_selector_all(
        "#eventKind option", "opts => opts.map(o => o.value)")
    for kind in kinds:
        await page.select_option("#eventKind", kind)
        await page.wait_for_timeout(150)
        if await page.is_visible("#urgentForm"):
            break


#: Состояния, которые снимаются в обычном прогоне. Порядок такой же, как в
#: скилле `dispatcher-ux-review`.
STATES: dict[str, Callable[[Page], Awaitable[None]]] = {
    "empty": empty,
    "planned": planned,
    "unassigned": unassigned,
    "assumptions": assumptions,
    "detail": detail,
    "compare": compare,
    "risk": risk,
    "validate": validate,
    "replan-engineer": replan_engineer,
    "urgent": urgent,
}
