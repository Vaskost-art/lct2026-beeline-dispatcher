"""Сценарии съёмки для новой заявки в течение дня.

Предпросмотр задержки бригады не показывает, что стало с новой заявкой и
через сколько бригада приедет на аварию. Эти состояния снимаются отдельно,
чтобы проверка вёрстки следила и за ними.
"""
from collections.abc import Awaitable, Callable

from playwright.async_api import Page
from shoot_steps import PLAN_TIMEOUT_MS, plan_day


async def _new_order(page: Page, work: str) -> None:
    """Раскрыть полосу события и заполнить новую заявку нужного типа."""
    await plan_day(page)
    await page.click('button:has-text("Событие в течение дня")')
    # По точному имени: подпись свёрнутой полосы тоже содержит «новая заявка».
    kind = page.get_by_role("button", name="Новая заявка", exact=True)
    await kind.wait_for(state="visible", timeout=30_000)
    await kind.scroll_into_view_if_needed()
    await kind.click()
    work_select = page.locator('label:has-text("Что пришло") select')
    await work_select.wait_for(state="visible", timeout=30_000)
    await work_select.select_option(label=work)
    await page.locator('label:has-text("Район") select').select_option(index=1)
    await page.click('button:has-text("Посмотреть, что изменится")')
    await page.wait_for_selector('[data-testid="new-order-outcome"]',
                                 timeout=PLAN_TIMEOUT_MS)


async def emergency_preview(page: Page) -> None:
    """Авария днём: к кому встала и через сколько бригада приедет."""
    await _new_order(page, "Авария")


async def ordinary_preview(page: Page) -> None:
    """Ремонт днём: встаёт только в свободное окно, соседей не двигает."""
    await _new_order(page, "Ремонт у клиента")


#: Подключаются в общий перечень запускателем съёмки.
EVENT_STATES: dict[str, Callable[[Page], Awaitable[None]]] = {
    "emergency-preview": emergency_preview,
    "ordinary-preview": ordinary_preview,
}
