'use strict';

/* Картографический слой.
 *
 * Две реализации за одним интерфейсом:
 *   «Яндекс Карты»  - JS API 3.0, российский сервис, нужен ключ;
 *   «Схема»         - собственная отрисовка на SVG, без сторонних библиотек
 *                     и без обращений наружу, работает офлайн.
 *
 * Схема - не заглушка: на защите или в поле интернета может не быть, а план
 * смотреть всё равно нужно. Она показывает те же маршруты и точки, подписывает
 * районы и даёт масштабную линейку, чтобы расстояния читались без подложки.
 *
 * Интерфейс: createDispatcherMap(container, options) -> объект с методами
 *   render(model)            - отрисовать маршруты и точки;
 *   focusOrder(orderId)      - подсветить точку;
 *   setTheme('dark'|'light') - переключить оформление;
 *   setPickMarker(lat, lon)  - поставить метку выбранной точки;
 *   clearPickMarker().
 *
 * model = {
 *   routes: [{ id, color, points: [{ lat, lon, kind, label, title, orderId }] }],
 *   loose:  [{ lat, lon, title, orderId }]
 * }
 * kind: 'base' - стартовая точка исполнителя, 'stop' - визит.
 */

import { createSchemeMap } from './scheme.js';
import { createYandexMap } from './yandex.js';

/* Возвращает карту, готовую к работе. Если ключ Яндекс Карт не задан или
   сервис не отвечает, молча переходит на схему и сообщает об этом
   через options.onFallback - чтобы интерфейс мог честно назвать источник. */
export async function createDispatcherMap(container, options) {
  const opts = options || {};
  if (opts.apiKey) {
    try {
      return await createYandexMap(container, opts);
    } catch (error) {
      if (opts.onFallback) opts.onFallback(error.message);
    }
  }
  return createSchemeMap(container, opts);
}
