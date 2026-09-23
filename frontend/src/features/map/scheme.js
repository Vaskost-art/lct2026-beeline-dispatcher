'use strict';

import { attachSchemeInput } from './scheme-input.js';
import { createViewport, districtLabels, escapeHtml } from './viewport.js';

/* Схематическая карта: собственная отрисовка на SVG, без сторонних
 * библиотек и без обращений наружу, работает офлайн. Не заглушка: на
 * защите или в поле интернета может не быть, а план смотреть всё равно
 * нужно. Показывает те же маршруты и точки, подписывает районы и даёт
 * масштабную линейку, чтобы расстояния читались без подложки. */
export function createSchemeMap(container, options) {
  const onPick = options.onPick || (() => {});
  const onSelectOrder = options.onSelectOrder || (() => {});

  container.innerHTML =
    '<div class="scheme-districts"></div>' +
    '<svg class="scheme-lines" aria-hidden="true">' +
    '<g class="scheme-routes"></g></svg>' +
    '<div class="scheme-markers"></div>' +
    '<div class="scheme-controls">' +
    '<button type="button" data-act="in" title="Приблизить">+</button>' +
    '<button type="button" data-act="out" title="Отдалить">−</button>' +
    '<button type="button" data-act="fit" title="Показать весь план">⤢</button>' +
    '</div>' +
    '<div class="scheme-scale"><span class="scheme-scale-bar"></span>' +
    '<span class="scheme-scale-text"></span></div>' +
    '<div class="scheme-note">Схема без картографической подложки: ' +
    'расстояния по прямой, районы подписаны</div>';

  const svg = container.querySelector('.scheme-lines');
  const routesGroup = container.querySelector('.scheme-routes');
  const markerLayer = container.querySelector('.scheme-markers');
  const districtLayer = container.querySelector('.scheme-districts');
  const scaleBar = container.querySelector('.scheme-scale-bar');
  const scaleText = container.querySelector('.scheme-scale-text');

  const viewport = createViewport(container);
  const { size, toScreen } = viewport;
  let model = { routes: [], loose: [] };
  let markers = [];          // { el, orderId }
  let pick = null;           // { lat, lon }

  function allPoints() {
    const out = [];
    model.routes.forEach((route) => route.points.forEach((p) => out.push(p)));
    model.loose.forEach((p) => out.push(p));
    if (pick) out.push(pick);
    return out;
  }

  function fit() {
    if (viewport.fitTo(allPoints())) draw();
  }

  function drawRoutes() {
    let lines = '';
    model.routes.forEach((route) => {
      if (route.points.length < 2) return;
      const d = route.points
        .map((p, i) => {
          const s = toScreen(p.lat, p.lon);
          return `${i ? 'L' : 'M'}${s.x.toFixed(1)} ${s.y.toFixed(1)}`;
        })
        .join(' ');
      const dim = route.dim ? ' class="dim"' : '';
      const stroke = route.dim ? '#c7ccd4' : route.color;
      lines += `<path d="${d}" stroke="${escapeHtml(stroke)}"${dim} />`;
    });
    routesGroup.innerHTML = lines;
  }

  function drawDistricts(w, h) {
    districtLayer.innerHTML = '';
    districtLabels(model).forEach((d) => {
      const s = toScreen(d.lat, d.lon);
      if (s.x < -60 || s.y < -20 || s.x > w + 60 || s.y > h + 20) return;
      const node = document.createElement('div');
      node.className = 'scheme-label';
      node.textContent = d.name;
      node.style.left = `${s.x}px`;
      node.style.top = `${s.y - 26}px`;
      districtLayer.appendChild(node);
    });
  }

  function place(p, html, cls, color) {
    const s = toScreen(p.lat, p.lon);
    const node = document.createElement('div');
    node.className = cls;
    node.innerHTML = html;
    if (color) node.style.background = color;
    node.style.left = `${s.x}px`;
    node.style.top = `${s.y}px`;
    if (p.title) node.title = p.title;
    if (p.orderId) {
      node.dataset.orderId = p.orderId;
      node.onclick = (event) => {
        event.stopPropagation();
        onSelectOrder(p.orderId);
      };
    }
    markerLayer.appendChild(node);
    markers.push({ el: node, orderId: p.orderId });
  }

  function draw() {
    const { w, h } = size();
    svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
    drawRoutes();
    drawDistricts(w, h);

    markerLayer.innerHTML = '';
    markers = [];
    model.routes.forEach((route) => {
      const faded = route.dim ? ' dim' : '';
      route.points.forEach((p) => {
        if (p.kind === 'base') {
          place(p, '', 'scheme-pin scheme-base' + faded, route.color);
        } else {
          place(p, escapeHtml(p.label || ''), 'scheme-pin' + faded, route.color);
        }
      });
    });
    model.loose.forEach((p) => place(p, '<span style="transform:rotate(-45deg)">!</span>',
                                     'scheme-pin scheme-loose'));
    if (pick) place(pick, '+', 'scheme-pin scheme-pick');

    const bar = viewport.scale();
    scaleBar.style.width = `${bar.px}px`;
    scaleText.textContent = bar.text;
  }

  const detach = attachSchemeInput(container, viewport, draw, fit, onPick);
  const onResize = () => draw();
  window.addEventListener('resize', onResize);

  return {
    kind: 'scheme',
    title: 'Схема',
    ready: Promise.resolve(),
    render(next) {
      const first = !model.routes.length && !model.loose.length;
      model = next || { routes: [], loose: [] };
      if (first) fit(); else draw();
    },
    fit,
    focusOrder(orderId) {
      markers.forEach((m) => {
        m.el.classList.toggle('selected', m.orderId === orderId);
      });
    },
    setTheme() { draw(); },
    setPickMarker(lat, lon) { pick = { lat, lon, title: 'Новая срочная заявка' }; draw(); },
    clearPickMarker() { pick = null; draw(); },
    destroy() {
      window.removeEventListener('resize', onResize);
      detach();
    },
  };
}
