'use strict';

/* Картографический слой.
 *
 * Две реализации за одним интерфейсом:
 *   «Яндекс Карты»  — JS API 3.0, российский сервис, нужен ключ;
 *   «Схема»         — собственная отрисовка на SVG, без сторонних библиотек
 *                     и без обращений наружу, работает офлайн.
 *
 * Схема — не заглушка: на защите или в поле интернета может не быть, а план
 * смотреть всё равно нужно. Она показывает те же маршруты и точки, подписывает
 * районы и даёт масштабную линейку, чтобы расстояния читались без подложки.
 *
 * Интерфейс: createDispatcherMap(container, options) -> объект с методами
 *   render(model)            — отрисовать маршруты и точки;
 *   focusOrder(orderId)      — подсветить точку;
 *   setTheme('dark'|'light') — переключить оформление;
 *   setPickMarker(lat, lon)  — поставить метку выбранной точки;
 *   clearPickMarker().
 *
 * model = {
 *   routes: [{ id, color, points: [{ lat, lon, kind, label, title, orderId }] }],
 *   loose:  [{ lat, lon, title, orderId }]
 * }
 * kind: 'base' — стартовая точка исполнителя, 'stop' — визит.
 */

(function () {
  const YANDEX_SCRIPT_TIMEOUT_MS = 12000;

  // --- проекция Меркатора, в градусах ---------------------------------------
  const RAD = Math.PI / 180;
  const projectY = (lat) =>
    Math.log(Math.tan(Math.PI / 4 + (lat * RAD) / 2)) / RAD;
  const unprojectY = (y) =>
    (Math.atan(Math.exp(y * RAD)) * 2 - Math.PI / 2) / RAD;

  const KM_PER_DEG_LON = 111.32;

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // =========================================================================
  //  Схематическая карта
  // =========================================================================

  function createSchemeMap(container, options) {
    const onPick = options.onPick || (() => {});
    const onSelectOrder = options.onSelectOrder || (() => {});

    container.innerHTML =
      '<svg class="scheme-lines" aria-hidden="true">' +
      '<g class="scheme-grid"></g><g class="scheme-routes"></g></svg>' +
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
    const gridGroup = container.querySelector('.scheme-grid');
    const routesGroup = container.querySelector('.scheme-routes');
    const markerLayer = container.querySelector('.scheme-markers');
    const scaleBar = container.querySelector('.scheme-scale-bar');
    const scaleText = container.querySelector('.scheme-scale-text');

    let model = { routes: [], loose: [] };
    let view = { cx: 37.62, cy: projectY(55.75), scale: 3000 };
    let markers = [];          // { el, x, y, orderId }
    let pick = null;           // { lat, lon }
    let dragged = false;

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

    function allPoints() {
      const out = [];
      model.routes.forEach((route) => route.points.forEach((p) => out.push(p)));
      model.loose.forEach((p) => out.push(p));
      if (pick) out.push(pick);
      return out;
    }

    function fit() {
      const points = allPoints();
      if (!points.length) return;
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
      draw();
    }

    function zoomAt(factor, px, py) {
      const { w, h } = size();
      const anchorX = px === undefined ? w / 2 : px;
      const anchorY = py === undefined ? h / 2 : py;
      const before = toLatLon(anchorX, anchorY);
      view.scale = Math.max(200, Math.min(4e6, view.scale * factor));
      const after = toLatLon(anchorX, anchorY);
      view.cx += before.lon - after.lon;
      view.cy += projectY(before.lat) - projectY(after.lat);
      draw();
    }

    function drawScale() {
      const { w } = size();
      const centerLat = unprojectY(view.cy);
      const kmPerPx = (KM_PER_DEG_LON * Math.cos(centerLat * RAD)) / view.scale;
      const target = Math.min(150, Math.max(70, w * 0.12));
      const roughKm = kmPerPx * target;
      const steps = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500];
      const km = steps.find((s) => s >= roughKm) || steps[steps.length - 1];
      scaleBar.style.width = `${Math.round(km / kmPerPx)}px`;
      scaleText.textContent = km < 1 ? `${km * 1000} м` : `${km} км`;
    }

    function drawGrid() {
      const { w, h } = size();
      svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
      const stepPx = 90;
      let out = '';
      for (let x = stepPx / 2; x < w; x += stepPx) {
        out += `<line x1="${x}" y1="0" x2="${x}" y2="${h}"/>`;
      }
      for (let y = stepPx / 2; y < h; y += stepPx) {
        out += `<line x1="0" y1="${y}" x2="${w}" y2="${y}"/>`;
      }
      gridGroup.innerHTML = out;
    }

    function districtLabels() {
      // Без подложки нужен хоть какой-то ориентир: подписываем районы
      // в центре тяжести их точек.
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

    function draw() {
      const { w, h } = size();
      drawGrid();

      let lines = '';
      model.routes.forEach((route) => {
        if (route.points.length < 2) return;
        const d = route.points
          .map((p, i) => {
            const s = toScreen(p.lat, p.lon);
            return `${i ? 'L' : 'M'}${s.x.toFixed(1)} ${s.y.toFixed(1)}`;
          })
          .join(' ');
        lines += `<path d="${d}" stroke="${escapeHtml(route.color)}" />`;
      });
      routesGroup.innerHTML = lines;

      markerLayer.innerHTML = '';
      markers = [];

      districtLabels().forEach((d) => {
        const s = toScreen(d.lat, d.lon);
        if (s.x < -60 || s.y < -20 || s.x > w + 60 || s.y > h + 20) return;
        const node = document.createElement('div');
        node.className = 'scheme-label';
        node.textContent = d.name;
        node.style.left = `${s.x}px`;
        node.style.top = `${s.y}px`;
        markerLayer.appendChild(node);
      });

      const place = (p, html, cls, color) => {
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
      };

      model.routes.forEach((route) => {
        route.points.forEach((p) => {
          if (p.kind === 'base') {
            place(p, '', 'scheme-pin scheme-base', route.color);
          } else {
            place(p, escapeHtml(p.label || ''), 'scheme-pin', route.color);
          }
        });
      });
      model.loose.forEach((p) => place(p, '!', 'scheme-pin scheme-loose'));
      if (pick) place(pick, '+', 'scheme-pin scheme-pick');

      drawScale();
    }

    // --- взаимодействие ---
    // Перетаскивание слушаем на окне, а не через захват указателя на
    // контейнере: захват перенаправляет события на контейнер, и клик
    // по метке до неё уже не доходит.
    let drag = null;

    const onMove = (event) => {
      if (!drag) return;
      const dx = event.clientX - drag.x;
      const dy = event.clientY - drag.y;
      if (Math.abs(dx) > 3 || Math.abs(dy) > 3) dragged = true;
      if (!dragged) return;
      view.cx = drag.cx - dx / view.scale;
      view.cy = drag.cy + dy / view.scale;
      draw();
    };
    const onUp = () => {
      drag = null;
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onUp);
    };

    container.addEventListener('pointerdown', (event) => {
      if (event.target.closest('.scheme-controls')) return;
      drag = { x: event.clientX, y: event.clientY, cx: view.cx, cy: view.cy };
      dragged = false;
      window.addEventListener('pointermove', onMove);
      window.addEventListener('pointerup', onUp);
      window.addEventListener('pointercancel', onUp);
    });

    container.addEventListener('wheel', (event) => {
      event.preventDefault();
      const rect = container.getBoundingClientRect();
      zoomAt(event.deltaY < 0 ? 1.2 : 1 / 1.2,
             event.clientX - rect.left, event.clientY - rect.top);
    }, { passive: false });

    container.addEventListener('click', (event) => {
      if (dragged || event.target.closest('.scheme-controls')) return;
      if (event.target.closest('.scheme-pin')) return;
      const rect = container.getBoundingClientRect();
      const at = toLatLon(event.clientX - rect.left, event.clientY - rect.top);
      onPick(at.lat, at.lon);
    });

    container.querySelector('.scheme-controls').onclick = (event) => {
      const act = event.target.dataset.act;
      if (act === 'in') zoomAt(1.4);
      if (act === 'out') zoomAt(1 / 1.4);
      if (act === 'fit') fit();
    };

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
        onUp();
      },
    };
  }

  // =========================================================================
  //  Яндекс Карты, JS API 3.0
  // =========================================================================

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

  async function createYandexMap(container, options) {
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
      } catch (_) { /* без кнопок масштаба карта всё равно работает */ }
    }

    const onPick = options.onPick || (() => {});
    const onSelectOrder = options.onSelectOrder || (() => {});

    let drawn = [];
    let pickMarker = null;
    let selected = null;
    const markerNodes = new Map();

    map.addChild(new window.ymaps3.YMapListener({
      onClick: (_object, event) => {
        if (!event || !event.coordinates) return;
        onPick(event.coordinates[1], event.coordinates[0]);
      },
    }));

    function clear() {
      drawn.forEach((child) => { try { map.removeChild(child); } catch (_) { /* уже снят */ } });
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
        if (bounds.length > 1) {
          const lons = bounds.map((b) => b[0]);
          const lats = bounds.map((b) => b[1]);
          map.update({
            location: {
              bounds: [
                [Math.min(...lons), Math.max(...lats)],
                [Math.max(...lons), Math.min(...lats)],
              ],
            },
          });
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
      destroy() { try { map.destroy(); } catch (_) { /* уже уничтожена */ } },
    };
  }

  // =========================================================================

  /* Возвращает карту, готовую к работе. Если ключ Яндекс Карт не задан или
     сервис не отвечает, молча переходит на схему и сообщает об этом
     через options.onFallback — чтобы интерфейс мог честно назвать источник. */
  window.createDispatcherMap = async function (container, options) {
    const opts = options || {};
    if (opts.apiKey) {
      try {
        return await createYandexMap(container, opts);
      } catch (error) {
        if (opts.onFallback) opts.onFallback(error.message);
      }
    }
    return createSchemeMap(container, opts);
  };
})();
