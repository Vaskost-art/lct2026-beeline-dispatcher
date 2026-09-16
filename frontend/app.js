'use strict';

/* Веб-интерфейс диспетчера: карта, маршруты, объяснения и перепланирование.
   Сторонних библиотек нет вообще. Карта живёт в map.js: при заданном ключе
   это Яндекс Карты, иначе собственная схема, которая работает офлайн. */

const S = {
  meta: null,
  region: null,
  plan: null,
  selected: null,
  hidden: new Set(),      // исполнители, скрытые на карте
  pickTarget: null,       // ожидание клика по карте для срочной заявки
  legendOpen: false,      // список бригад поверх карты свёрнут по умолчанию
  mapFallbackReason: '',  // почему вместо Яндекс Карт показана схема
};

const $ = (id) => document.getElementById(id);
const el = (tag, cls, html) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (html !== undefined) node.innerHTML = html;
  return node;
};
const esc = (s) => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;');

/* Стабильный цвет исполнителя: золотое сечение по кругу оттенков даёт
   хорошо различимые цвета при любом числе бригад. */
const colorOf = (i) => `hsl(${Math.round((i * 137.508) % 360)} 72% 58%)`;
const COLORS = new Map();
const engineerColor = (id) => COLORS.get(id) || '#7d8da8';

const isLocked = (orderId) =>
  Boolean(S.plan && S.plan.locked && S.plan.locked[orderId]);
const isApprox = (order) => Boolean(order) && order.geocode_precision === 'approx_district';

const plural = (n, one, few, many) => {
  const a = Math.abs(n) % 100;
  if (a > 10 && a < 20) return many;
  const b = a % 10;
  if (b === 1) return one;
  if (b > 1 && b < 5) return few;
  return many;
};

function openTab(name) {
  document.querySelectorAll('.tab').forEach((tab) => {
    const active = tab.dataset.tab === name;
    tab.classList.toggle('active', active);
    $(`tab-${tab.dataset.tab}`).hidden = !active;
  });
}

/* Блок «как это считается»: методология нужна, но не на первом экране. */
const howBlock = (title, body) =>
  `<details class="how"><summary>${esc(title)}</summary>
     <div class="how-body">${body}</div></details>`;

/* ---------- оформление: день, ночь, как в системе ---------- */

const THEME_KEY = 'dispatcher-theme';
const THEME_MODES = ['system', 'light', 'dark'];

function readTheme() {
  try {
    const stored = localStorage.getItem(THEME_KEY);
    return THEME_MODES.includes(stored) ? stored : 'system';
  } catch (_) {
    return 'system';       // приватный режим: просто следуем за системой
  }
}

function currentTheme() {
  const explicit = document.documentElement.getAttribute('data-theme');
  if (explicit) return explicit;
  return window.matchMedia
    && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

function applyTheme(mode) {
  const root = document.documentElement;
  if (mode === 'light' || mode === 'dark') root.setAttribute('data-theme', mode);
  else root.removeAttribute('data-theme');

  try { localStorage.setItem(THEME_KEY, mode); } catch (_) { /* не критично */ }

  document.querySelectorAll('.theme-btn').forEach((button) => {
    button.setAttribute('aria-pressed', String(button.dataset.mode === mode));
  });
  if (map) map.setTheme(currentTheme());
}

function initTheme() {
  applyTheme(readTheme());
  document.querySelectorAll('.theme-btn').forEach((button) => {
    button.onclick = () => applyTheme(button.dataset.mode);
  });
}

/* ---------- сеть ---------- */

async function api(path, options) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (_) { data = null; }
  if (!res.ok) {
    const detail = (data && (data.detail || data.message)) || text || res.statusText;
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return data;
}

/* Расчёт занимает до полутора десятков секунд. Без обратной связи это
   выглядит как зависший интерфейс. */
function setLoading(on, what, howLong) {
  const wrap = document.querySelector('.map-wrap');
  const existing = $('loading');
  if (!on) { if (existing) existing.remove(); return; }
  const node = existing || el('div', 'loading');
  node.id = 'loading';
  node.innerHTML = `<div class="spinner"></div>
    <div class="what">${esc(what)}</div>` +
    (howLong ? `<div class="how-long">${esc(howLong)}</div>` : '');
  if (!existing) wrap.appendChild(node);
}

let toastTimer = null;
function toast(message) {
  const node = $('toast');
  node.textContent = message;
  node.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { node.hidden = true; }, 6000);
}

async function busy(button, fn) {
  /* Подпись запоминается один раз за жизнь кнопки: если взять её текущий
     текст, второй параллельный запрос запомнит «Считаем…» и оставит это
     на кнопке навсегда. */
  if (button && !button.dataset.label) button.dataset.label = button.textContent;
  if (button) { button.disabled = true; button.textContent = 'Считаем…'; }
  try { return await fn(); }
  catch (err) { toast(err.message || String(err)); return null; }
  finally {
    if (button) { button.disabled = false; button.textContent = button.dataset.label; }
  }
}

/* ---------- карта ---------- */

let map = null;

async function initMap() {
  map = await createDispatcherMap($('map'), {
    apiKey: S.meta.map_api_key || null,
    theme: currentTheme(),
    onFallback: (why) => {
      // Ключ не задан или сервис не ответил: говорим об этом прямо,
      // а не делаем вид, что так и задумано.
      S.mapFallbackReason = why;
    },
    onSelectOrder: (orderId) => selectOrder(orderId),
    onPick: (lat, lon) => {
      if (!S.pickTarget || !$('replanBar').open) return;
      $('uLat').value = lat.toFixed(6);
      $('uLon').value = lon.toFixed(6);
      $('uAddress').value = `Точка на карте ${lat.toFixed(4)}, ${lon.toFixed(4)}`;
      $('pickHint').textContent =
        `Точка задана: ${lat.toFixed(4)}, ${lon.toFixed(4)}`;
      map.setPickMarker(lat, lon);
      drawPlan();
    },
  });
  describeMapSource();
}

function describeMapSource() {
  const node = $('mapSource');
  if (!node || !map) return;
  if (map.kind === 'yandex') {
    node.textContent = 'Карта: Яндекс Карты';
    node.title = '';
    return;
  }
  node.textContent = 'Карта: схема без подложки';
  node.title = S.mapFallbackReason
    ? `${S.mapFallbackReason}. Показана собственная схема.`
    : 'Ключ Яндекс Карт не задан — показана собственная схема. '
      + 'Как подключить, написано в README.';
}

/* Собирает то, что карте нужно нарисовать. Сама карта ничего не знает
   ни про заявки, ни про смены — только точки, линии и подписи. */
function buildMapModel() {
  const orders = new Map(S.plan.orders.map((o) => [o.id, o]));
  const engineers = new Map(S.plan.engineers.map((e) => [e.id, e]));

  const routes = [];
  S.plan.routes.forEach((route) => {
    if (S.hidden.has(route.engineer_id)) return;
    const engineer = engineers.get(route.engineer_id);
    const color = engineerColor(route.engineer_id);
    const points = [];

    if (engineer) {
      points.push({
        lat: engineer.lat, lon: engineer.lon, kind: 'base',
        title: `${engineer.name} · база участка\n`
             + `Смена ${engineer.shift_start}–${engineer.shift_end} · ${engineer.vehicle}`,
      });
    }
    route.stops.forEach((stop, index) => {
      const order = orders.get(stop.order_id);
      if (!order) return;
      points.push({
        lat: order.lat, lon: order.lon, kind: 'stop',
        label: String(index + 1), orderId: order.id, district: order.district,
        title: `${stop.start}–${stop.end} · ${route.engineer_id}\n`
             + `${order.district}, ${order.address}`,
      });
    });
    if (points.length > 1) routes.push({ id: route.engineer_id, color, points });
  });

  const reasons = new Map(S.plan.unassigned.map((u) => [u.order_id, u.reason_text]));
  const loose = S.plan.orders
    .filter((o) => reasons.has(o.id))
    .map((o) => ({
      lat: o.lat, lon: o.lon, orderId: o.id, district: o.district,
      title: `Заявка ${o.id} — не назначена\n${reasons.get(o.id)}`,
    }));

  return { routes, loose };
}

function drawPlan() {
  if (!map || !S.plan) return;
  map.render(buildMapModel());
  if (S.selected) map.focusOrder(S.selected);
  $('mapHint').hidden = true;
}

/* ---------- метрики ---------- */

function renderMetrics() {
  const box = $('metrics');
  const m = S.plan.metrics;
  box.hidden = false;
  box.innerHTML = '';

  const add = (key, value, cls, sub, hint) => {
    const node = el('div', `metric ${cls || ''}`);
    if (hint) node.title = hint;
    node.appendChild(el('div', 'k', esc(key)));
    node.appendChild(el('div', 'v', value + (sub ? ` <small>${esc(sub)}</small>` : '')));
    box.appendChild(node);
  };

  // Четыре числа, по которым диспетчер судит о плане. Всё остальное —
  // в подсказках и в сравнении вариантов, чтобы полоса не превращалась в отчёт.
  const share = Math.round(m.assigned_share * 100);
  add('Назначено', `${m.orders_assigned}<small>/${m.orders_total}</small>`,
      share === 100 ? 'good' : (share >= 90 ? '' : 'warn'), `${share}%`);
  add('Людей в смене', `${m.used_engineers}`, 'good', `из ${m.engineers_available}`,
      'Сколько исполнителей получили хотя бы одну заявку');
  add('Пробег', `${m.total_km.toFixed(1)}`, '', 'км',
      `В среднем ${m.avg_km_per_order.toFixed(1)} км на заявку`);
  add('В пути', `${Math.round(m.travel_share * 100)}`, '', '%',
      `${m.total_travel_min} мин в дороге против ${m.total_work_min} мин на работах`);

  if (m.orders_unassigned > 0) {
    const alert = el('button', 'metric alert');
    alert.type = 'button';
    alert.innerHTML =
      `<div class="k">Без исполнителя</div>
       <div class="v">${m.orders_unassigned}
         <small>${plural(m.orders_unassigned, 'заявка', 'заявки', 'заявок')} · причины</small></div>`;
    alert.onclick = () => openTab('unassigned');
    box.appendChild(alert);
  }
}

/* Строка под метриками отвечает на два вопроса, которые диспетчер задаёт
   перед тем, как разослать маршруты: можно ли доверять расчёту и можно ли
   доверять километрам. Оба ответа приходят с планом. */
function renderPlanNotes() {
  const box = $('planNotes');
  const notes = [];

  const status = S.plan.solver_status_text;
  if (status && status.level !== 'ok') {
    notes.push({ level: status.level, text: status.text });
  }

  const geo = S.plan.geo;
  if (geo && geo.approx_count) notes.push({ level: geo.level, text: geo.text });

  if (S.plan.restored) {
    notes.push({
      level: 'note',
      text: `Загружен сохранённый день «${S.plan.restored.name}»`
        + (S.plan.restored.saved_at ? ` от ${S.plan.restored.saved_at.replace('T', ' ')}` : '')
        + '.',
    });
  }

  if (!notes.length) { box.hidden = true; box.innerHTML = ''; return; }
  box.hidden = false;
  box.innerHTML = '';
  notes.forEach((n) => {
    const node = el('div', `note note-${esc(n.level)}`);
    node.appendChild(el('span', 'note-text', esc(n.text)));
    box.appendChild(node);
  });
}

/* ---------- список маршрутов ---------- */

function renderRoutes() {
  const box = $('tab-routes');
  box.innerHTML = '';
  const orders = new Map(S.plan.orders.map((o) => [o.id, o]));
  const summaries = new Map(S.plan.route_summaries.map((r) => [r.engineer_id, r]));
  const risk = new Map((S.plan.risk ? S.plan.risk.routes : [])
    .map((r) => [r.engineer_id, r]));

  if (!S.plan.routes.length) {
    box.appendChild(el('div', 'empty', '<p>Ни одного маршрута не построено.</p>'));
    return;
  }

  S.plan.routes.forEach((route) => {
    const color = engineerColor(route.engineer_id);
    const node = el('div', 'route');
    node.style.setProperty('--dot', color);

    const routeRisk = risk.get(route.engineer_id);
    const head = el('div', 'route-head');
    head.appendChild(el('div', 'route-name',
      (routeRisk ? `<span class="risk-dot risk-${esc(routeRisk.risk)}"
        title="Запас прочности маршрута: ${routeRisk.tolerance_min} мин"></span>` : '')
      + esc(route.engineer_id)));
    head.appendChild(el('div', 'route-stat',
      `${route.stops.length} ${plural(route.stops.length, 'заявка', 'заявки', 'заявок')} · ${route.total_km.toFixed(1)} км`));
    head.onclick = () => node.classList.toggle('open');
    node.appendChild(head);

    const body = el('div', 'route-body');
    const summary = summaries.get(route.engineer_id);
    if (summary) body.appendChild(el('div', 'route-summary', esc(summary.summary)));
    if (routeRisk) body.appendChild(el('div', 'route-summary', esc(routeRisk.text)));

    const stopRisk = new Map((routeRisk ? routeRisk.stops : [])
      .map((s) => [s.order_id, s]));

    route.stops.forEach((stop, i) => {
      const order = orders.get(stop.order_id);
      if (!order) return;
      const sr = stopRisk.get(order.id);
      const row = el('div', 'stop');
      row.dataset.orderId = order.id;
      row.innerHTML = `
        <div class="stop-n">${i + 1}</div>
        <div style="flex:1;min-width:0">
          <div><span class="stop-time">${esc(stop.start)}–${esc(stop.end)}</span>
            <span class="badge">${esc(order.id)}</span>
            ${order.priority === 'Срочная' ? '<span class="badge urgent">срочная</span>' : ''}
            ${isLocked(order.id) ? '<span class="badge pinned" title="Заявка закреплена за этим исполнителем — планировщик её не переносит">закреплена</span>' : ''}
            ${isApprox(order) ? '<span class="badge approx" title="Адрес не разрешён точно: взят центр района, пробег до точки — оценка">≈ адрес</span>' : ''}
            ${order.required_vehicle ? '<span class="badge car">' + esc(order.required_vehicle) + '</span>' : ''}
            ${sr && sr.risk !== 'низкий'
              ? `<span class="badge risk ${esc(sr.risk)}" title="Запас до срыва окна">запас ${sr.tolerance_min} мин</span>`
              : ''}
          </div>
          <div class="stop-where">${esc(order.district)}, ${esc(order.address)}</div>
          <div class="stop-meta">${esc(order.type_hd)} · ${order.duration_min} мин ·
            в пути ${stop.travel_min} мин / ${stop.travel_km.toFixed(1)} км
            ${stop.wait_min ? ' · ожидание ' + stop.wait_min + ' мин' : ''}</div>
        </div>`;
      row.onclick = () => selectOrder(order.id);
      body.appendChild(row);
    });

    node.appendChild(body);
    box.appendChild(node);
  });
}

function renderUnassigned() {
  const box = $('tab-unassigned');
  box.innerHTML = '';
  $('unassignedCount').textContent = S.plan.unassigned.length;
  if (!S.plan.unassigned.length) {
    box.appendChild(el('div', 'empty',
      '<h3>Все заявки распределены</h3><p>Ни одна заявка не осталась без исполнителя.</p>'));
    return;
  }
  const orders = new Map(S.plan.orders.map((o) => [o.id, o]));
  S.plan.unassigned.forEach((u) => {
    const order = orders.get(u.order_id);
    const card = el('div', 'card');
    card.innerHTML = `
      <div class="card-id">Заявка ${esc(u.order_id)}
        ${order && order.priority === 'Срочная' ? '<span class="badge urgent">срочная</span>' : ''}
        ${isLocked(u.order_id) ? '<span class="badge pinned" title="Заявка закреплена за бригадой — планировщик не предлагает её другим">закреплена</span>' : ''}
        ${isApprox(order) ? '<span class="badge approx" title="Адрес не разрешён точно: взят центр района">≈ адрес</span>' : ''}</div>
      ${order ? `<div class="card-meta">${esc(order.district)}, ${esc(order.address)}<br>
         ${esc(order.type_hd)} · окно ${esc(order.window_start)}–${esc(order.window_end)} ·
         ${order.duration_min} мин · навык: ${esc(order.required_skill)}</div>` : ''}
      <div class="card-why">${esc(u.reason_text)}</div>`;
    card.onclick = () => selectOrder(u.order_id);
    box.appendChild(card);
  });
}

function renderAssumptions() {
  const box = $('tab-assumptions');
  box.innerHTML = '';
  box.appendChild(el('div', 'empty',
    '<h3>Откуда берутся цифры</h3><p>Длительность работ, навыки бригад, транспорт ' +
    'и границы смен в выгрузках не приходят — планировщик достраивает их ' +
    'по правилам ниже.</p>'));
  S.meta.assumptions.forEach((a) => {
    const node = el('div', 'assumption');
    node.appendChild(el('h4', null, esc(a.title)));
    node.appendChild(el('p', null, esc(a.text)));
    box.appendChild(node);
  });
}

function renderLegend() {
  const box = $('mapLegend');
  box.hidden = false;
  box.innerHTML = '';

  const head = el('button', 'legend-title');
  head.type = 'button';
  const count = S.plan.routes.length;
  head.textContent =
    `${count} ${plural(count, 'исполнитель', 'исполнителя', 'исполнителей')}`;
  head.setAttribute('aria-expanded', String(S.legendOpen));
  head.onclick = () => { S.legendOpen = !S.legendOpen; renderLegend(); };
  box.appendChild(head);
  if (!S.legendOpen) return;

  S.plan.routes.forEach((route) => {
    const row = el('div', 'legend-row' + (S.hidden.has(route.engineer_id) ? ' off' : ''));
    const dot = el('span', 'legend-dot');
    dot.style.background = engineerColor(route.engineer_id);
    row.appendChild(dot);
    row.appendChild(el('span', null,
      `${esc(route.engineer_id)} · ${route.total_km.toFixed(1)} км`));
    row.onclick = () => {
      if (S.hidden.has(route.engineer_id)) S.hidden.delete(route.engineer_id);
      else S.hidden.add(route.engineer_id);
      drawPlan(); renderLegend();
    };
    box.appendChild(row);
  });
}

/* ---------- карточка заявки с объяснением ---------- */

let explainGeneration = 0;

async function selectOrder(orderId) {
  const generation = ++explainGeneration;
  S.selected = orderId;
  document.querySelectorAll('.stop').forEach((n) => {
    n.classList.toggle('selected', n.dataset.orderId === orderId);
  });
  if (map) map.focusOrder(orderId);

  const data = await busy(null, () => api('/api/explain', {
    method: 'POST',
    body: JSON.stringify({ region: S.region, order_id: orderId }),
  }));
  if (data && generation === explainGeneration) renderDetail(data);
}

/* Возврат панели к исходному виду: то же, что лежит в разметке до первого
   выбора заявки. */
function clearDetail() {
  $('detail').innerHTML =
    `<div class="empty">
       <h3>Объяснение назначения</h3>
       <p>Выберите заявку на карте или в списке маршрутов.</p>
     </div>`;
}

function renderDetail(data) {
  const box = $('detail');
  box.innerHTML = '';
  const order = (S.plan.orders || []).find((o) => o.id === data.order_id);

  // Заголовок уже называет исполнителя и место в маршруте, поэтому в подзаголовок
  // идёт то, чего в нём нет: где и в какое окно.
  const head = el('div', 'detail-head');
  head.appendChild(el('h3', null, esc(data.headline)));
  if (order) {
    head.appendChild(el('div', 'sub',
      `${esc(order.district)}, ${esc(order.address)} · окно ` +
      `${esc(order.window_start)}–${esc(order.window_end)}`));
  }
  box.appendChild(head);

  const summary = el('div', 'detail-section');
  summary.appendChild(el('h4', null, data.assigned ? 'Почему так' : 'Почему не назначена'));
  summary.appendChild(el('div', 'summary-box' + (data.assigned ? '' : ' bad'),
    esc(data.assigned ? data.summary : data.reason)));
  box.appendChild(summary);

  // Передать заявку — сразу под объяснением: диспетчер прочитал причину
  // и здесь же решает, согласен он с ней или нет.
  const manual = el('div', 'detail-section');
  manual.appendChild(el('h4', null, 'Передать другому'));
  const wrap = el('div', 'reassign');
  const field = el('label', 'field');
  field.appendChild(el('span', null, 'Исполнитель'));
  const select = el('select');
  select.appendChild(new Option(data.assigned ? '— снять с исполнителя —' : '— не назначена —', ''));
  S.plan.engineers.forEach((e) => {
    const option = new Option(e.id, e.id);
    if (e.id === data.engineer_id) option.selected = true;
    select.appendChild(option);
  });
  field.appendChild(select);
  wrap.appendChild(field);

  const button = el('button', null, 'Применить');
  button.onclick = () => busy(button, async () => {
    const plan = await api('/api/reassign', {
      method: 'POST',
      body: JSON.stringify({
        region: S.region, order_id: data.order_id,
        engineer_id: select.value || null,
      }),
    });
    setPlan(plan);
    selectOrder(data.order_id);
  });
  wrap.appendChild(button);
  manual.appendChild(wrap);
  box.appendChild(manual);

  // Закрепление и приоритет меняют условия задачи, поэтому план после них
  // пересчитывается. Отделяем их от разового переноса «здесь и сейчас».
  const decisions = el('div', 'detail-section');
  decisions.appendChild(el('h4', null, 'Решения на весь день'));

  const lockedTo = (S.plan.locked || {})[data.order_id] || '';
  const lockRow = el('div', 'reassign');
  const lockField = el('label', 'field');
  lockField.appendChild(el('span', null, 'Закрепить за'));
  const lockSelect = el('select');
  lockSelect.title = 'Планировщик не будет переносить эту заявку на другого '
    + 'исполнителя ни при пересчёте, ни при перепланировании дня';
  lockSelect.appendChild(new Option('— не закреплена —', ''));
  S.plan.engineers.forEach((e) => {
    const option = new Option(e.id, e.id);
    if (e.id === lockedTo) option.selected = true;
    lockSelect.appendChild(option);
  });
  lockField.appendChild(lockSelect);
  lockRow.appendChild(lockField);

  const prioField = el('label', 'field');
  prioField.appendChild(el('span', null, 'Приоритет'));
  const prioSelect = el('select');
  prioSelect.title = 'Срочные заявки планировщик снимает последними: '
    + 'за срочную он пожертвует несколькими обычными';
  (S.meta.priorities || ['Обычная', 'Срочная']).forEach((value) => {
    const option = new Option(value, value);
    if (order && order.priority === value) option.selected = true;
    prioSelect.appendChild(option);
  });
  prioField.appendChild(prioSelect);
  lockRow.appendChild(prioField);

  const applyButton = el('button', null, 'Пересчитать');
  applyButton.onclick = () => busy(applyButton, async () => {
    const body = {
      region: S.region, order_id: data.order_id,
      set_lock: true, lock_to: lockSelect.value || null,
      time_limit_sec: Number($('timeLimit').value) || 15,
    };
    if (order && prioSelect.value !== order.priority) body.priority = prioSelect.value;
    setLoading(true, 'Пересчитываем план с учётом правки');
    try {
      const plan = await api('/api/order/adjust',
        { method: 'POST', body: JSON.stringify(body) });
      if (plan) { setPlan(plan); selectOrder(data.order_id); }
    } finally {
      setLoading(false);
    }
  });
  lockRow.appendChild(applyButton);
  decisions.appendChild(lockRow);
  box.appendChild(decisions);

  if (data.assigned) {
    const timing = el('div', 'detail-section');
    timing.appendChild(el('h4', null, 'Время и дорога'));
    timing.appendChild(el('div', 'reason-line', esc(data.timing_reason)));
    timing.appendChild(el('div', 'reason-line', esc(data.route_reason)));
    box.appendChild(timing);
  }

  if (data.alternatives && data.alternatives.length) {
    const alts = el('div', 'detail-section');
    const total = data.alternatives_total || data.alternatives.length;
    alts.appendChild(el('h4', null,
      `Кто ещё мог взять — проверено ${total}`));
    data.alternatives.forEach((a) => {
      const row = el('div', 'alt');
      const tagClass = a.possible ? 'ok'
        : (a.blocked_by === 'Навык' ? 'skill'
          : (a.blocked_by === 'Ресурс' ? 'res' : 'time'));
      row.innerHTML = `
        <span class="alt-tag ${tagClass}">${esc(a.possible ? 'мог бы' : a.blocked_by)}</span>
        <span class="alt-name">${esc(a.engineer_id)}</span>
        <span class="alt-why">${esc(a.reason)}</span>`;
      alts.appendChild(row);
    });
    box.appendChild(alts);
  }

  // Полный набор полей нужен редко: по умолчанию свёрнут.
  const facts = el('div', 'detail-section');
  const details = el('details', 'how');
  const rows = data.facts
    .map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('');
  details.innerHTML =
    `<summary>Все данные заявки</summary>
     <div class="how-body"><dl class="facts">${rows}</dl></div>`;
  facts.appendChild(details);
  box.appendChild(facts);
}

/* ---------- планирование ---------- */

function setPlan(plan) {
  S.plan = plan;
  /* Объяснение относится к прежнему плану: оставить его на экране значит
     показывать диспетчеру исполнителя и время, которых больше нет. */
  if (S.selected && !plan.orders.some((o) => o.id === S.selected)) S.selected = null;
  clearDetail();
  plan.engineers.forEach((e, i) => { if (!COLORS.has(e.id)) COLORS.set(e.id, colorOf(i)); });
  renderMetrics();
  renderPlanNotes();
  renderUndo();
  renderRoutes();
  renderUnassigned();
  renderAssumptions();
  renderLegend();
  drawPlan();
  fillEventSelectors();
}

/* Номер поколения: ответ запроса, запущенного для прежнего района или
   отменённого более свежим запуском, применять нельзя. */
let planGeneration = 0;

async function runPlan(options) {
  const generation = ++planGeneration;
  const requestedRegion = S.region;
  const limit = Number($('timeLimit').value) || 15;
  const title = $('strategy').selectedOptions[0]
    ? $('strategy').selectedOptions[0].text.toLowerCase() : 'план';
  setLoading(true, `Считаем ${title}`,
    $('strategy').value === 'optimized' ? `около ${limit} с` : 'несколько секунд');
  try {
    const plan = await busy($('btnPlan'), () => api('/api/plan', {
      method: 'POST',
      body: JSON.stringify({
        region: S.region,
        strategy: $('strategy').value,
        time_limit_sec: limit,
        reset: Boolean(options && options.reset),
      }),
    }));
    if (plan && generation === planGeneration && requestedRegion === S.region) {
      S.hidden.clear();
      setPlan(plan);
    }
  } finally {
    if (generation === planGeneration) setLoading(false);
  }
}

/* ---------- шаг назад, сохранение дня ---------- */

/* Кнопка называет то, что именно откатится: «Шаг назад» без предмета
   заставляет диспетчера гадать, что он потеряет. */
function renderUndo() {
  const button = $('btnUndo');
  const steps = (S.plan && S.plan.undo) || [];
  button.disabled = !steps.length;
  button.title = steps.length
    ? `Отменить: ${steps[0]}`
    : 'Отменять нечего: план ещё не менялся';
}

async function undoStep() {
  const plan = await busy($('btnUndo'),
    () => api('/api/undo', { method: 'POST', body: JSON.stringify({ region: S.region }) }));
  if (!plan) return;
  setPlan(plan);
  toast(`Отменено: ${plan.undone}`);
}

async function savePlan() {
  /* Без обработчика отказ выглядит как «ничего не произошло», и диспетчер
     уходит с мыслью, что день сохранён. */
  const data = await busy($('btnSave'), () => api('/api/plan/save', {
    method: 'POST', body: JSON.stringify({ region: S.region }),
  }));
  if (data) toast(`Рабочий день сохранён (${data.path})`);
}

async function restorePlan() {
  const info = await api(`/api/plan/saved/${encodeURIComponent(S.region)}`);
  if (!info) return;
  if (!info.exists) { toast('Сохранённого дня для этого района нет'); return; }
  const when = (info.saved_at || '').replace('T', ' ');
  if (!confirm(`Загрузить сохранённый день от ${when}?\n`
             + `Текущий план будет заменён — отменить это шагом назад нельзя.`)) return;
  setLoading(true, 'Поднимаем сохранённый день');
  try {
    const plan = await api('/api/plan/restore',
      { method: 'POST', body: JSON.stringify({ region: S.region }) });
    if (plan) { S.hidden.clear(); setPlan(plan); toast('Сохранённый день загружен'); }
  } finally {
    setLoading(false);
  }
}

async function resetManual() {
  if (!confirm('Снять все закрепления и вернуть исходные заявки и смены?\n'
             + 'Ручные правки этого дня будут потеряны.')) return;
  await runPlan({ reset: true });
  toast('Ручные правки сняты');
}

/* ---------- сравнение вариантов ---------- */

async function showCompare() {
  const limit = Number($('timeLimit').value) || 15;
  setLoading(true, 'Считаем все варианты плана',
    `около ${limit} с — каждый вариант считается отдельно`);
  let data;
  try {
    data = await busy($('btnCompare'),
      () => api(`/api/compare/${S.region}?time_limit_sec=${limit}`));
  } finally {
    setLoading(false);
  }
  if (!data) return;

  const base = data.rows.find((r) => r.key === 'baseline').metrics;
  const rows = data.rows.map((r) => ({ ...r, isOpt: r.key === 'optimized' }));

  const deltaCell = (value, reference, invert, unit) => {
    const diff = value - reference;
    if (Math.abs(diff) < 0.05) return `${value.toFixed(unit === 'км' ? 1 : 0)}`;
    const good = invert ? diff < 0 : diff > 0;
    return `${value.toFixed(unit === 'км' ? 1 : 0)}
      <span class="delta ${good ? 'good' : 'bad'}">${diff > 0 ? '+' : ''}${diff.toFixed(unit === 'км' ? 1 : 0)}</span>`;
  };

  let html = `<h2>Сравнение вариантов — ${esc(data.region_name)}</h2>
    <p class="lead">Как разошлись бы те же заявки при разных способах распределения.
    Последняя строка — как они разошлись на самом деле.</p>
    <table><thead><tr>
      <th>Вариант</th><th class="num">Назначено</th>
      <th class="num">Исполнителей</th><th class="num">Пробег, км</th>
      <th class="num">Км на заявку</th><th class="num">Расчёт, с</th>
    </tr></thead><tbody>`;

  rows.forEach((r) => {
    const m = r.metrics;
    html += `<tr class="${r.isOpt ? 'highlight' : ''}">
      <td><b>${esc(r.title)}</b></td>
      <td class="num">${deltaCell(m.orders_assigned, base.orders_assigned, false)}<small> / ${m.orders_total}</small></td>
      <td class="num">${deltaCell(m.used_engineers, base.used_engineers, true)}</td>
      <td class="num">${m.total_km.toFixed(1)}</td>
      <td class="num">${deltaCell(m.avg_km_per_order, base.avg_km_per_order, true, 'км')}</td>
      <td class="num">${m.solve_seconds.toFixed(2)}</td></tr>`;
  });

  const fm = data.fact.metrics;
  html += `<tr class="fact">
      <td><b>${esc(data.fact.title)}</b></td>
      <td class="num">${fm.orders_assigned}<small> / ${fm.orders_total}</small></td>
      <td class="num">${fm.used_engineers}</td>
      <td class="num">${fm.total_km.toFixed(1)}</td>
      <td class="num">${fm.avg_km_per_order.toFixed(1)}</td>
      <td class="num">—</td></tr>`;
  html += '</tbody></table>';

  const vb = data.vs_baseline, vf = data.vs_fact;
  const sign = (x) => (x >= 0 ? '+' : '') + x;
  const pctText = (x) => (x !== null && x !== undefined ? sign(x) + '%' : '—');

  if (data.basis) html += `<div class="modal-note">${esc(data.basis)}</div>`;
  html += `<div class="modal-note">
    <b>Оптимальный план против распределения без планировщика:</b>
    заявок ${sign(vb.orders_assigned_delta)},
    людей ${sign(vb.used_engineers_delta)} (${pctText(vb.used_engineers_pct)}),
    километров на заявку ${sign(vb.km_per_order_delta)} (${pctText(vb.km_per_order_pct)}).<br><br>
    <b>Против того, как заявки разошлись на самом деле:</b>
    людей ${sign(vf.used_engineers_delta)} (${pctText(vf.used_engineers_pct)}),
    километров на заявку ${sign(vf.km_per_order_delta)} (${pctText(vf.km_per_order_pct)}).</div>`;

  html += howBlock('Почему сравниваем именно так', `
    <p><b>Суммарный пробег между вариантами несопоставим.</b> План, раздавший
    вдвое меньше заявок, «экономит» километры просто потому, что многого не
    делает: вариант без оптимизации закрывает ${base.orders_assigned} заявок
    из ${base.orders_total} и поэтому проезжает мало. Сопоставима удельная
    величина, километры на одну назначенную заявку, она в отдельном столбце.</p>
    <p><b>Быстрый расчёт добавлен намеренно.</b> Вариант без оптимизации задан
    в техническом задании и намеренно наивен; сравнивать оптимальный план
    только с ним было бы некорректно, поэтому в таблице есть и сильная
    промежуточная эвристика.</p>
    <p><b>По числу заявок с фактом сравнивать нельзя.</b>
    ${esc(data.fact.report.note)}
    Нарушений правила «начало работ внутри окна» в фактическом распределении:
    <b>${data.fact.report.window_violations.length}</b>, выходов за границы
    смены: <b>${data.fact.report.shift_overflow.length}</b>.</p>`);

  openModal(html);
}

/* ---------- прогноз опозданий ---------- */

async function showRisk(overrun) {
  const minutes = overrun === undefined ? 15 : overrun;
  const data = await busy(overrun === undefined ? $('btnRisk') : null,
    () => api(`/api/risk/${S.region}?overrun=${minutes}`));
  if (!data) return;
  S.risk = data;

  const th = data.thresholds;
  let html = `<h2>Прогноз опозданий</h2>
    <p class="lead">Где план порвётся первым, если работы затянутся.</p>
    <div class="summary-box${data.by_risk['высокий'] ? ' bad' : ''}">${esc(data.summary)}</div>`;

  html += `<div class="slider-row">
      <label for="overrunRange" style="font-size:12px;color:var(--muted)">
        Если каждая работа затянется на</label>
      <input type="range" id="overrunRange" min="0" max="60" step="5" value="${minutes}">
      <output id="overrunOut">${minutes} мин</output>
    </div>`;

  const cs = data.custom_scenario;
  html += `<div class="modal-note" id="overrunNote">${esc(cs.text)}</div>`;

  if (cs.broken.length) {
    html += `<table style="margin-top:14px"><thead><tr><th>Заявка</th>
      <th>Исполнитель</th><th>Район</th><th>Окно</th><th>Приоритет</th>
      </tr></thead><tbody>`;
    cs.broken.slice(0, 40).forEach((b) => {
      html += `<tr><td>${esc(b.order_id)}</td><td>${esc(b.engineer_id)}</td>
        <td>${esc(b.district)}</td><td>${esc(b.window)}</td>
        <td>${b.priority === 'Срочная'
          ? '<span class="badge urgent">срочная</span>' : '—'}</td></tr>`;
    });
    if (cs.broken.length > 40) {
      html += `<tr><td colspan="5">…и ещё ${cs.broken.length - 40}</td></tr>`;
    }
    html += '</tbody></table>';
  }

  html += `<h2 style="margin-top:22px;font-size:14px">Запас прочности маршрутов</h2>
    <table><thead><tr><th>Исполнитель</th><th class="num">Запас, мин</th>
    <th class="num">Опоздание с выезда, мин</th><th>Слабое место</th>
    </tr></thead><tbody>`;
  data.routes.forEach((r) => {
    html += `<tr><td><span class="risk-dot risk-${esc(r.risk)}"></span>
      ${esc(r.engineer_id)}</td>
      <td class="num">${r.tolerance_min}</td>
      <td class="num">${r.start_tolerance_min}</td>
      <td>визит №${r.weakest_position}, заявка ${esc(r.weakest_order_id)}</td></tr>`;
  });
  html += '</tbody></table>';

  html += howBlock('Как считается запас прочности', `
    <p>План по нормативам всегда выглядит выполнимым, но в реальном дне работы
    затягиваются. Запас прочности считается прямым пересчётом маршрута: при
    какой задержке начало работ перестаёт попадать в окно или маршрут выходит
    за смену. Это не вероятность, а граница, её можно проверить вручную.</p>
    <p>Высокий риск — запас меньше ${th.high_below} мин, средний — меньше
    ${th.medium_below}. «Опоздание с выезда» больше запаса потому, что задержку
    на старте поглощает ожидание открытия окон дальше по маршруту.</p>`);

  openModal(html);

  const range = $('overrunRange');
  if (range) {
    range.oninput = () => { $('overrunOut').textContent = `${range.value} мин`; };
    range.onchange = () => showRisk(Number(range.value));
  }
}

/* ---------- загрузка и выгрузка набора данных ---------- */

async function uploadDataset(file) {
  if (!file) return;
  const data = await busy($('btnUpload'), async () => {
    const res = await fetch(
      `/api/dataset/upload?filename=${encodeURIComponent(file.name)}`,
      { method: 'POST', body: file });
    const text = await res.text();
    let payload = null;
    try { payload = text ? JSON.parse(text) : null; } catch (_) { payload = null; }
    if (!res.ok) {
      throw new Error((payload && payload.detail) || text || res.statusText);
    }
    return payload;
  });
  if (!data) return;

  // пересобираем список районов: загруженный набор встаёт рядом со встроенными
  S.meta = await api('/api/meta');
  const region = $('region');
  region.innerHTML = '';
  S.meta.regions.forEach((r) => {
    region.appendChild(new Option(
      `${r.builtin ? '' : '↑ '}${r.region_name} — ${r.orders} заявок, ${r.engineers} инженеров`,
      r.region_key));
  });
  region.value = data.region;
  S.region = data.region;
  S.hidden.clear();
  COLORS.clear();
  toast(`Набор загружен (${data.format}): ${data.summary.orders} заявок, ` +
        `${data.summary.engineers} исполнителей`);
  await runPlan();
}

function currentRegionMeta() {
  return (S.meta.regions || []).find((r) => r.region_key === S.region) || null;
}

/* Подставляет в форму событие, пришедшее вместе с набором данных. */
function applyDatasetEvent() {
  const meta = currentRegionMeta();
  const event = meta && meta.dataset_events && meta.dataset_events[0];
  if (!event) return;

  $('eventKind').value = event.kind || 'urgent_order';
  onEventKindChange();
  if (event.at) $('eventAt').value = event.at;
  if (event.order_id) $('eventOrder').value = event.order_id;
  if (event.engineer_id) $('eventEngineer').value = event.engineer_id;

  const order = event.new_order;
  if (order) {
    $('uId').value = order.id || 'URGENT-1';
    $('uLat').value = order.lat;
    $('uLon').value = order.lon;
    $('uAddress').value = order.address || '';
    if (order.district) {
      const districts = $('uDistrict');
      if (![...districts.options].some((o) => o.value === order.district)) {
        districts.appendChild(new Option(order.district, order.district));
      }
      districts.value = order.district;
    }
    if (order.duration_min) $('uDuration').value = order.duration_min;
    if (order.window_start) $('uFrom').value = order.window_start;
    if (order.window_end) $('uTo').value = order.window_end;
    if (order.required_skill) $('uSkill').value = order.required_skill;
    $('uVehicle').value = order.required_vehicle || '';
    /* Координаты приходят из присланного файла: без проверки NaN уезжает
       в разметку схемы и гасит её целиком до перезагрузки страницы. */
    const lat = Number(order.lat);
    const lon = Number(order.lon);
    const hasPoint = Number.isFinite(lat) && Number.isFinite(lon);
    $('pickHint').textContent = hasPoint
      ? `Точка из набора: ${lat.toFixed(4)}, ${lon.toFixed(4)}`
      : 'В событии из набора нет координат — укажите точку на карте.';
    if (map && hasPoint) { map.setPickMarker(lat, lon); drawPlan(); }
  }
  toast('Событие из набора подставлено в форму');
}

/* ---------- независимая проверка ограничений ---------- */

async function showValidation() {
  const data = await busy($('btnValidate'), () => api(`/api/validate/${S.region}`));
  if (!data) return;

  let html = `<h2>Проверка плана</h2>
    <p class="lead">Проверено маршрутов: <b>${data.checked_routes}</b>,
    визитов: <b>${data.checked_stops}</b>.</p>`;

  if (data.ok) {
    html += `<div class="summary-box">Нарушений не найдено. У каждой заявки
      исполнитель с нужным навыком и транспортом, начало работ внутри окна,
      маршрут укладывается в смену.</div>`;
  } else {
    html += `<div class="summary-box bad">Найдено нарушений:
      ${data.violations.length}. Ниже — каждое с указанием правила.</div>
      <table style="margin-top:14px"><thead><tr><th>Правило</th>
      <th>Исполнитель</th><th>Заявка</th><th>Что не так</th></tr></thead><tbody>`;
    data.violations.forEach((v) => {
      html += `<tr><td><b>${esc(v.rule)}</b></td><td>${esc(v.engineer_id)}</td>
        <td>${esc(v.order_id)}</td><td>${esc(v.text)}</td></tr>`;
    });
    html += '</tbody></table>';
  }

  html += howBlock('Как устроена проверка', `
    <p>План перепроверяется отдельным модулем, который ничего не знает о том,
    как он был построен: маршруты пересчитываются с нуля и сверяются с тем,
    что показано на экране.</p>
    <p>Проверяются четыре вещи: требуемый навык заявки входит в навыки
    исполнителя; требуемый тип транспорта совпадает; начало работ попадает
    во временное окно, а маршрут укладывается в смену; времена и пробег
    на экране совпадают с пересчётом, и ни одна заявка не назначена дважды.</p>`);
  openModal(html);
}

/* ---------- перепланирование ---------- */

function fillEventSelectors() {
  const orderSelect = $('eventOrder');
  orderSelect.innerHTML = '';
  const assigned = new Set();
  S.plan.routes.forEach((r) => r.stops.forEach((s) => assigned.add(s.order_id)));
  S.plan.orders.filter((o) => assigned.has(o.id)).forEach((o) => {
    orderSelect.appendChild(new Option(
      `${o.id} · ${o.district} · ${o.window_start}–${o.window_end}`, o.id));
  });

  const engineerSelect = $('eventEngineer');
  engineerSelect.innerHTML = '';
  S.plan.routes.forEach((r) => {
    engineerSelect.appendChild(new Option(
      `${r.engineer_id} · ${r.stops.length} заявок`, r.engineer_id));
  });

  const meta = currentRegionMeta();
  $('btnFromDataset').hidden = !(meta && meta.dataset_events
                                 && meta.dataset_events.length);

  const districtSelect = $('uDistrict');
  /* Список собирается заново под текущий план: иначе после смены района или
     загрузки набора срочная заявка уйдёт с районом из прежних данных. */
  const districtsNow = [...new Set(S.plan.orders.map((o) => o.district))].sort();
  const districtsWere = [...districtSelect.options].map((o) => o.value);
  if (String(districtsWere) !== String(districtsNow)) {
    const chosen = districtSelect.value;
    districtSelect.innerHTML = '';
    districtsNow.forEach((d) => districtSelect.appendChild(new Option(d, d)));
    if (districtsNow.includes(chosen)) districtSelect.value = chosen;
  }
}

function onEventKindChange() {
  const kind = $('eventKind').value;
  $('fieldOrder').hidden = kind !== 'cancel_order';
  $('fieldEngineer').hidden = !(kind === 'engineer_unavailable' || kind === 'engineer_delayed');
  $('fieldDelay').hidden = kind !== 'engineer_delayed';
  $('urgentForm').hidden = kind !== 'urgent_order';
  S.pickTarget = kind === 'urgent_order';
  if (S.pickTarget) $('pickHint').textContent = 'Кликните по карте, чтобы задать точку аварии';
}

async function runReplan(apply) {
  const kind = $('eventKind').value;
  const body = {
    region: S.region, kind, at: $('eventAt').value,
    mode: $('eventMode').value, apply: !!apply,
    time_limit_sec: Number($('timeLimit').value) || 15,
  };
  if (kind === 'cancel_order') body.order_id = $('eventOrder').value;
  if (kind === 'engineer_unavailable') body.engineer_id = $('eventEngineer').value;
  if (kind === 'engineer_delayed') {
    body.engineer_id = $('eventEngineer').value;
    body.delay_min = Number($('eventDelay').value) || 45;
  }
  if (kind === 'urgent_order') {
    const lat = Number($('uLat').value), lon = Number($('uLon').value);
    if (!lat || !lon) { toast('Сначала кликните по карте — нужна точка новой заявки'); return; }
    body.new_order = {
      id: $('uId').value.trim() || 'URGENT-1',
      lat, lon,
      address: $('uAddress').value,
      district: $('uDistrict').value,
      duration_min: Number($('uDuration').value) || 90,
      window_start: $('uFrom').value,
      window_end: $('uTo').value,
      required_skill: $('uSkill').value,
      required_vehicle: $('uVehicle').value || null,
    };
  }

  setLoading(true, apply ? 'Применяем новый план' : 'Перестраиваем остаток дня');
  let data;
  try {
    data = await busy($('btnReplan'),
      () => api('/api/replan', { method: 'POST', body: JSON.stringify(body) }));
  } finally {
    setLoading(false);
  }
  if (!data) return;

  if (apply) {
    setPlan(data);
    closeModal();
    toast('План обновлён');
    return;
  }
  showDiff(data);
}

function showDiff(data) {
  const diff = data.diff;
  const orders = new Map(data.orders.map((o) => [o.id, o]));

  let html = `<h2>${esc(diff.event.title)} — ${esc(diff.event.at)}</h2>
    <p class="lead">Предварительный результат. Текущий план не изменится,
    пока вы не нажмёте «Применить».</p><ul class="narrative">`;
  data.narrative.forEach((line) => { html += `<li>${esc(line)}</li>`; });
  html += '</ul>';

  const t = diff.totals;
  const cell = (after, before, invert, digits) => {
    const d = after - before;
    const good = invert ? d < 0 : d > 0;
    return `${after.toFixed(digits)}${Math.abs(d) < 0.05 ? ''
      : ` <span class="delta ${good ? 'good' : 'bad'}">${d > 0 ? '+' : ''}${d.toFixed(digits)}</span>`}`;
  };
  html += `<table><thead><tr><th>Показатель</th><th class="num">Было</th>
    <th class="num">Стало</th></tr></thead><tbody>
    <tr><td>Назначено заявок</td><td class="num">${t.assigned_before}</td>
      <td class="num">${cell(t.assigned_after, t.assigned_before, false, 0)}</td></tr>
    <tr><td>Задействовано исполнителей</td><td class="num">${t.used_engineers_before}</td>
      <td class="num">${cell(t.used_engineers_after, t.used_engineers_before, true, 0)}</td></tr>
    <tr><td>Суммарный пробег, км</td><td class="num">${t.total_km_before.toFixed(1)}</td>
      <td class="num">${cell(t.total_km_after, t.total_km_before, true, 1)}</td></tr>
    </tbody></table>`;

  const interesting = diff.changes.filter((c) => c.status !== 'frozen');
  if (interesting.length) {
    html += `<h2 style="margin-top:20px;font-size:14px">Что изменилось в назначениях
      (${interesting.length})</h2><ul class="diff-list">`;
    const label = {
      added: 'добавлена', cancelled: 'снята', moved: 'передана',
      resequenced: 'переставлена', dropped: 'выпала', rescued: 'вернулась',
    };
    interesting.slice(0, 60).forEach((c) => {
      const order = orders.get(c.order_id);
      const where = c.status === 'moved'
        ? `${esc(c.from_engineer)} → <b>${esc(c.to_engineer)}</b>`
        : (c.to_engineer ? `<b>${esc(c.to_engineer)}</b>`
          : (c.from_engineer ? `была у ${esc(c.from_engineer)}` : '—'));
      html += `<li><span class="diff-badge b-${c.status}">${label[c.status] || c.status}</span>
        <b>${esc(c.order_id)}</b>${order ? ` · ${esc(order.district)} ·
        окно ${esc(order.window_start)}–${esc(order.window_end)}` : ''} — ${where}</li>`;
    });
    if (interesting.length > 60) {
      html += `<li>…и ещё ${interesting.length - 60}</li>`;
    }
    html += '</ul>';
  }

  if (diff.engineers.length) {
    html += `<h2 style="margin-top:20px;font-size:14px">Нагрузка исполнителей</h2>
      <table><thead><tr><th>Исполнитель</th><th class="num">Заявок было</th>
      <th class="num">Стало</th><th class="num">Пробег было</th>
      <th class="num">Стало</th></tr></thead><tbody>`;
    diff.engineers.forEach((r) => {
      html += `<tr><td>${esc(r.engineer_id)}</td>
        <td class="num">${r.orders_before}</td>
        <td class="num">${cell(r.orders_after, r.orders_before, false, 0)}</td>
        <td class="num">${r.km_before.toFixed(1)}</td>
        <td class="num">${cell(r.km_after, r.km_before, true, 1)}</td></tr>`;
    });
    html += '</tbody></table>';
  }

  html += '<div style="margin-top:20px;display:flex;gap:10px">' +
    '<button class="primary" id="btnApplyReplan">Применить</button>' +
    '<button id="btnCancelReplan">Оставить как было</button></div>';

  openModal(html);
  $('btnApplyReplan').onclick = () => runReplan(true);
  $('btnCancelReplan').onclick = closeModal;
}

/* ---------- меню «Данные» ---------- */

function initDataMenu() {
  const button = $('btnData');
  const list = $('dataMenu');
  const close = () => {
    list.hidden = true;
    button.setAttribute('aria-expanded', 'false');
  };
  button.onclick = (event) => {
    event.stopPropagation();
    const opening = list.hidden;
    list.hidden = !opening;
    button.setAttribute('aria-expanded', String(opening));
  };
  list.addEventListener('click', close);
  document.addEventListener('click', close);
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') close();
  });
}

/* Режимы перепланирования различаются ценой, а не названием,
   поэтому цена подписана прямо под выбором. */
function updateModeHint() {
  const mode = $('eventMode').value;
  const found = (S.meta.replan_modes || []).find((m) => m.key === mode);
  $('modeHint').textContent = found && found.hint ? found.hint : '';
}

/* ---------- модальное окно ---------- */

function openModal(html) { $('modalBody').innerHTML = html; $('modal').hidden = false; }
function closeModal() { $('modal').hidden = true; }

/* ---------- запуск ---------- */

async function init() {
  initTheme();
  initDataMenu();

  // скрытые поля координат срочной заявки
  const form = $('urgentForm');
  ['uLat', 'uLon'].forEach((id) => {
    const input = el('input'); input.type = 'hidden'; input.id = id; form.appendChild(input);
  });

  S.meta = await api('/api/meta');
  await initMap();

  const region = $('region');
  S.meta.regions.forEach((r) => {
    region.appendChild(new Option(
      `${r.builtin ? '' : '↑ '}${r.region_name} — ${r.orders} заявок, ${r.engineers} инженеров`,
      r.region_key));
  });
  S.region = region.value;
  region.onchange = () => { S.region = region.value; S.hidden.clear(); runPlan(); };

  const strategy = $('strategy');
  S.meta.strategies.forEach((item) => {
    const option = new Option(item.title, item.key);
    if (item.hint) option.title = item.hint;
    strategy.appendChild(option);
  });
  strategy.value = 'optimized';
  const describeStrategy = () => {
    const found = S.meta.strategies.find((item) => item.key === strategy.value);
    strategy.title = found && found.hint ? found.hint : 'Как распределять заявки';
  };
  strategy.onchange = describeStrategy;
  describeStrategy();

  const kind = $('eventKind');
  S.meta.replan_kinds.forEach((k) => kind.appendChild(new Option(k.title, k.key)));
  kind.onchange = onEventKindChange;

  const mode = $('eventMode');
  S.meta.replan_modes.forEach((m) => mode.appendChild(new Option(m.title, m.key)));
  mode.onchange = updateModeHint;
  updateModeHint();

  S.meta.skills.forEach((s) => $('uSkill').appendChild(new Option(s, s)));
  $('uVehicle').appendChild(new Option('— без ограничения —', ''));
  S.meta.vehicles.forEach((v) => $('uVehicle').appendChild(new Option(v, v)));
  $('uSkill').value = 'Аварийные работы';

  $('btnPlan').onclick = () => runPlan();
  $('btnCompare').onclick = () => showCompare();
  $('btnValidate').onclick = () => showValidation();
  $('btnRisk').onclick = () => showRisk();
  $('btnExport').onclick = () => window.open(`/api/export/${S.region}`, '_blank');
  $('btnDataset').onclick = () => window.open(`/api/dataset/${S.region}`, '_blank');
  $('btnUpload').onclick = () => $('fileInput').click();
  $('btnUndo').onclick = () => undoStep();
  $('btnSave').onclick = () => savePlan();
  $('btnRestore').onclick = () => restorePlan();
  $('btnReset').onclick = () => resetManual();
  $('fileInput').onchange = (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = '';           // тот же файл можно выбрать повторно
    uploadDataset(file);
  };
  $('btnFromDataset').onclick = () => applyDatasetEvent();
  $('btnReplan').onclick = () => runReplan(false);
  $('modalClose').onclick = closeModal;
  $('modal').onclick = (e) => { if (e.target === $('modal')) closeModal(); };
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModal(); });

  document.querySelectorAll('.tab').forEach((tab) => {
    tab.onclick = () => openTab(tab.dataset.tab);
  });

  onEventKindChange();
  await runPlan();
}

init().catch((err) => toast('Не удалось запустить интерфейс: ' + err.message));
