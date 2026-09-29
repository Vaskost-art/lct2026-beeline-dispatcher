'use strict';

/* Картографический слой.
 *
 * Три реализации за одним интерфейсом:
 *   «Яндекс Карты»  - JS API 3.0, российский сервис, нужен ключ;
 *   «OpenStreetMap» - подложка OpenStreetMap на Leaflet, без ключа и без платы;
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

/* Возвращает карту, готовую к работе. Яндекс Карты при ключе, иначе
   OpenStreetMap, а без сети - собственная схема. О каждом переходе
   сообщает через options.onFallback, чтобы интерфейс честно назвал источник. */
/* Leaflet грузится отдельным файлом и только когда нужен. */
async function createOsmMap(container, options) {
  const { createOsmMap: create } = await import('./osm.js');
  return create(container, options);
}

export async function createDispatcherMap(container, options) {
  const opts = options || {};
  const attempts = opts.apiKey ? [createYandexMap, createOsmMap] : [createOsmMap];
  for (const create of attempts) {
    try {
      return await create(container, opts);
    } catch (error) {
      if (opts.onFallback) opts.onFallback(error.message);
    }
  }
  return createSchemeMap(container, opts);
}
