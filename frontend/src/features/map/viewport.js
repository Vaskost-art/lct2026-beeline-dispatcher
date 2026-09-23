'use strict';

/* Геометрия схемы: проекция Меркатора, перевод координат в пиксели и
 * обратно, линейка масштаба, подписи районов. Без обращения к DOM, кроме
 * размеров контейнера, поэтому схема и её обработчики делят одни расчёты. */

export const RAD = Math.PI / 180;
export const projectY = (lat) => Math.log(Math.tan(Math.PI / 4 + (lat * RAD) / 2)) / RAD;
export const unprojectY = (y) => (Math.atan(Math.exp(y * RAD)) * 2 - Math.PI / 2) / RAD;

const KM_PER_DEG_LON = 111.32;

export function escapeHtml(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/* Вид схемы над контейнером. `view` меняется на месте: его держат и
   отрисовка, и перетаскивание. */
export function createViewport(container) {
  const view = { cx: 37.62, cy: projectY(55.75), scale: 3000 };

  const size = () => ({
    w: container.clientWidth || 800,
    h: container.clientHeight || 600,
  });

  const toScreen = (lat, lon) => {
    const { w, h } = size();
    return {
      x: (lon - view.cx) * view.scale + w / 2,
      y: (view.cy - projectY(lat)) * view.scale + h / 2,
    };
  };

  const toLatLon = (x, y) => {
    const { w, h } = size();
    return {
      lon: (x - w / 2) / view.scale + view.cx,
      lat: unprojectY(view.cy - (y - h / 2) / view.scale),
    };
  };

  /* Вписать точки в контейнер с полями под подписи. */
  function fitTo(points) {
    if (!points.length) return false;
    const { w, h } = size();
    const xs = points.map((p) => p.lon);
    const ys = points.map((p) => projectY(p.lat));
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    view.cx = (minX + maxX) / 2;
    view.cy = (minY + maxY) / 2;
    const dx = Math.max(maxX - minX, 1e-4);
    const dy = Math.max(maxY - minY, 1e-4);
    view.scale = Math.min((w - 90) / dx, (h - 90) / dy);
    return true;
  }

  /* Приблизить с сохранением точки под курсором. */
  function zoomAt(factor, px, py) {
    const { w, h } = size();
    const anchorX = px === undefined ? w / 2 : px;
    const anchorY = py === undefined ? h / 2 : py;
    const before = toLatLon(anchorX, anchorY);
    view.scale = Math.max(200, Math.min(4e6, view.scale * factor));
    const after = toLatLon(anchorX, anchorY);
    view.cx += before.lon - after.lon;
    view.cy += projectY(before.lat) - projectY(after.lat);
  }

  /* Линейка: ширина в пикселях и подпись. */
  function scale() {
    const { w } = size();
    const centerLat = unprojectY(view.cy);
    const kmPerPx = (KM_PER_DEG_LON * Math.cos(centerLat * RAD)) / view.scale;
    const target = Math.min(150, Math.max(70, w * 0.12));
    const steps = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500];
    // Ближайший круглый шаг, а не первый больший: «первый больший» давал
    // полосу вдвое шире задуманной, и линейка растягивалась через пол-карты.
    const km = steps.reduce((best, step) =>
      Math.abs(step / kmPerPx - target) < Math.abs(best / kmPerPx - target) ? step : best,
    steps[0]);
    return { px: Math.round(km / kmPerPx), text: km < 1 ? `${km * 1000} м` : `${km} км` };
  }

  return { view, size, toScreen, toLatLon, fitTo, zoomAt, scale };
}

/* Подписи районов в центре тяжести их точек: без подложки нужен хоть
   какой-то ориентир. */
export function districtLabels(model) {
  const groups = new Map();
  const add = (p) => {
    if (!p.district) return;
    const item = groups.get(p.district) || { lat: 0, lon: 0, n: 0 };
    item.lat += p.lat; item.lon += p.lon; item.n += 1;
    groups.set(p.district, item);
  };
  model.routes.forEach((r) => r.points.forEach(add));
  model.loose.forEach(add);
  return [...groups.entries()].map(([name, g]) => ({
    name, lat: g.lat / g.n, lon: g.lon / g.n, count: g.n,
  }));
}
