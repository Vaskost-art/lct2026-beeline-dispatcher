'use strict';

import { escapeHtml } from './viewport.js';

/* Яндекс Карты, JS API 3.0: российский сервис, нужен ключ. Если скрипт не
 * ответил за отведённое время, вызывающий переходит на собственную схему. */

const YANDEX_SCRIPT_TIMEOUT_MS = 12000;

function loadYandexScript(apiKey) {
  return new Promise((resolve, reject) => {
    if (window.ymaps3) { resolve(); return; }
    const script = document.createElement('script');
    script.src = 'https://api-maps.yandex.ru/v3/?apikey=' +
      encodeURIComponent(apiKey) + '&lang=ru_RU';
    script.async = true;
    const timer = setTimeout(
      () => reject(new Error('Яндекс Карты не ответили')),
      YANDEX_SCRIPT_TIMEOUT_MS);
    script.onload = () => { clearTimeout(timer); resolve(); };
    script.onerror = () => {
      clearTimeout(timer);
      reject(new Error('Не удалось загрузить Яндекс Карты'));
    };
    document.head.appendChild(script);
  });
}

export async function createYandexMap(container, options) {
  await loadYandexScript(options.apiKey);
  await window.ymaps3.ready;

  const {
    YMap, YMapDefaultSchemeLayer, YMapDefaultFeaturesLayer,
    YMapMarker, YMapFeature, YMapControls,
  } = window.ymaps3;

  container.innerHTML = '';
  const map = new YMap(container, {
    location: { center: [37.62, 55.75], zoom: 10 },
  });
  const scheme = new YMapDefaultSchemeLayer({
    theme: options.theme === 'light' ? 'light' : 'dark',
  });
  map.addChild(scheme);
  map.addChild(new YMapDefaultFeaturesLayer());
  if (YMapControls) {
    try {
      const { YMapZoomControl } = window.ymaps3.import
        ? await window.ymaps3.import('@yandex/ymaps3-controls@0.0.1') : {};
      if (YMapZoomControl) {
        const controls = new YMapControls({ position: 'right' });
        controls.addChild(new YMapZoomControl({}));
        map.addChild(controls);
      }
    } catch { /* без кнопок масштаба карта всё равно работает */ }
  }

  const onPick = options.onPick || (() => {});
  const onSelectOrder = options.onSelectOrder || (() => {});

  let drawn = [];
  let pickMarker = null;
  let selected = null;
  let fitted = false;
  let lastBounds = [];

  function fitBounds(points) {
    const lons = points.map((p) => p[0]);
    const lats = points.map((p) => p[1]);
    map.update({
      location: {
        bounds: [
          [Math.min(...lons), Math.max(...lats)],
          [Math.max(...lons), Math.min(...lats)],
        ],
      },
    });
  }
  const markerNodes = new Map();

  map.addChild(new window.ymaps3.YMapListener({
    onClick: (_object, event) => {
      if (!event || !event.coordinates) return;
      onPick(event.coordinates[1], event.coordinates[0]);
    },
  }));

  function clear() {
    drawn.forEach((child) => { try { map.removeChild(child); } catch { /* уже снят */ } });
    drawn = [];
    markerNodes.clear();
  }

  function addMarker(point, html, cls, color, orderId) {
    const node = document.createElement('div');
    node.className = cls;
    node.innerHTML = html;
    if (color) node.style.background = color;
    if (point.title) node.title = point.title;
    if (orderId) {
      node.onclick = (event) => { event.stopPropagation(); onSelectOrder(orderId); };
      markerNodes.set(orderId, node);
    }
    const marker = new YMapMarker(
      { coordinates: [point.lon, point.lat] }, node);
    map.addChild(marker);
    drawn.push(marker);
  }

  return {
    kind: 'yandex',
    title: 'Яндекс Карты',
    ready: Promise.resolve(),
    render(model) {
      clear();
      const bounds = [];
      (model.routes || []).forEach((route) => {
        const coords = route.points.map((p) => [p.lon, p.lat]);
        coords.forEach((c) => bounds.push(c));
        if (coords.length > 1) {
          const line = new YMapFeature({
            geometry: { type: 'LineString', coordinates: coords },
            style: { stroke: [{ color: route.color, width: 3 }] },
          });
          map.addChild(line);
          drawn.push(line);
        }
        route.points.forEach((p) => {
          if (p.kind === 'base') {
            addMarker(p, '', 'scheme-pin scheme-base', route.color);
          } else {
            addMarker(p, escapeHtml(p.label || ''), 'scheme-pin',
                      route.color, p.orderId);
          }
        });
      });
      (model.loose || []).forEach((p) => {
        bounds.push([p.lon, p.lat]);
        addMarker(p, '!', 'scheme-pin scheme-loose', null, p.orderId);
      });
      if (pickMarker) {
        addMarker(pickMarker, '+', 'scheme-pin scheme-pick');
      }
      /* Масштаб подбираем только при первой отрисовке плана. Дальше карту
         двигает диспетчер: иначе клик по легенде или выбор точки аварии
         отбрасывал бы приближенный квартал обратно на весь район.
         Общий вид возвращается методом fit() и штатным зумом карты. */
      lastBounds = bounds;
      if (bounds.length > 1 && !fitted) {
        fitted = true;
        fitBounds(bounds);
      }
      if (selected) this.focusOrder(selected);
    },
    focusOrder(orderId) {
      selected = orderId;
      markerNodes.forEach((node, id) => {
        node.classList.toggle('selected', id === orderId);
      });
    },
    setTheme(theme) {
      scheme.update({ theme: theme === 'light' ? 'light' : 'dark' });
    },
    setPickMarker(lat, lon) {
      pickMarker = { lat, lon, title: 'Новая срочная заявка' };
    },
    clearPickMarker() { pickMarker = null; },
    /* Вернуть общий вид: карта сама масштаб больше не сбрасывает. */
    fit() {
      if (lastBounds.length > 1) fitBounds(lastBounds);
    },
    destroy() { try { map.destroy(); } catch { /* уже уничтожена */ } },
  };
}
