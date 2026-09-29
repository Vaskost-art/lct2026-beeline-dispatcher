'use strict';

import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

import { escapeHtml } from './viewport.js';

/* Карта OpenStreetMap: без ключа и без платы. Метки и линии те же, что на
 * схеме и на Яндекс Картах. Подложка приглушена стилями (map.css), чтобы
 * цвета бригад читались поверх неё. Если плитки не пришли (нет интернета),
 * вызывающий переходит на собственную схему. */

const TILES = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
const ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
const PROBE_TIMEOUT_MS = 6000;
const MOSCOW = [55.75, 37.62];

/* Одна плитка Москвы: отвечает подложка или нет. Без проверки карта без
   сети показывала бы серое поле с линиями вместо понятной схемы. */
function probeTiles() {
  return new Promise((resolve, reject) => {
    const image = new Image();
    const timer = setTimeout(
      () => reject(new Error('Подложка OpenStreetMap не ответила')), PROBE_TIMEOUT_MS);
    image.onload = () => { clearTimeout(timer); resolve(); };
    image.onerror = () => {
      clearTimeout(timer);
      reject(new Error('Не удалось загрузить подложку OpenStreetMap'));
    };
    image.src = TILES.replace('{z}', '10').replace('{x}', '619').replace('{y}', '320');
  });
}

function pinIcon(html, cls, color) {
  const style = color ? ` style="background:${escapeHtml(color)}"` : '';
  return L.divIcon({
    className: 'osm-pin-anchor',
    html: `<div class="${cls}"${style}>${html}</div>`,
    iconSize: [0, 0],
  });
}

export async function createOsmMap(container, options) {
  await probeTiles();

  container.innerHTML = '';
  const map = L.map(container, { zoomControl: false, attributionControl: false })
    .setView(MOSCOW, 10);
  L.control.zoom({ position: 'topleft' }).addTo(map);
  L.control.attribution({ position: 'bottomleft', prefix: false })
    .addAttribution(ATTRIBUTION).addTo(map);
  L.tileLayer(TILES, { maxZoom: 19 }).addTo(map);
  container.classList.toggle('osm-dark', options.theme === 'dark');
  const layer = L.layerGroup().addTo(map);

  const onPick = options.onPick || (() => {});
  const onSelectOrder = options.onSelectOrder || (() => {});
  map.on('click', (event) => onPick(event.latlng.lat, event.latlng.lng));

  const markerNodes = new Map();
  let pickMarker = null;
  let selected = null;
  let fitted = false;
  let lastBounds = [];

  function addMarker(point, html, cls, color, orderId) {
    const marker = L.marker([point.lat, point.lon], {
      icon: pinIcon(html, cls, color), keyboard: false, title: point.title || '',
    }).addTo(layer);
    if (orderId) {
      marker.on('click', () => onSelectOrder(orderId));
      const node = marker.getElement()?.firstElementChild;
      if (node) markerNodes.set(orderId, node);
    }
  }

  function fitBounds(points) {
    map.fitBounds(L.latLngBounds(points), { padding: [36, 36], animate: false });
  }

  return {
    kind: 'osm',
    title: 'OpenStreetMap',
    ready: Promise.resolve(),
    render(model) {
      // Контейнер мог поменять размер: без этого часть плиток не догружалась.
      map.invalidateSize();
      layer.clearLayers();
      markerNodes.clear();
      const bounds = [];
      (model.routes || []).forEach((route) => {
        const coords = route.points.map((p) => [p.lat, p.lon]);
        coords.forEach((c) => bounds.push(c));
        if (coords.length > 1) {
          L.polyline(coords, {
            color: route.dim ? '#c7ccd4' : route.color,
            weight: route.dim ? 2 : 3,
            opacity: route.dim ? 0.7 : 0.9,
            interactive: false,
          }).addTo(layer);
        }
        const faded = route.dim ? ' dim' : '';
        route.points.forEach((p) => {
          if (p.kind === 'base') {
            addMarker(p, '', 'scheme-pin scheme-base' + faded, route.color);
          } else {
            addMarker(p, escapeHtml(p.label || ''), 'scheme-pin' + faded,
                      route.color, p.orderId);
          }
        });
      });
      (model.loose || []).forEach((p) => {
        bounds.push([p.lat, p.lon]);
        addMarker(p, '!', 'scheme-pin scheme-loose', null, p.orderId);
      });
      if (pickMarker) addMarker(pickMarker, '+', 'scheme-pin scheme-pick');
      /* Масштаб подбираем только при первой отрисовке плана, как и на
         Яндекс Картах: дальше карту двигает диспетчер. */
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
    setTheme(theme) { container.classList.toggle('osm-dark', theme === 'dark'); },
    setPickMarker(lat, lon) {
      pickMarker = { lat, lon, title: 'Новая срочная заявка' };
    },
    clearPickMarker() { pickMarker = null; },
    fit() {
      if (lastBounds.length > 1) fitBounds(lastBounds);
    },
    destroy() { map.remove(); },
  };
}
