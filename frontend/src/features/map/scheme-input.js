'use strict';

/* Мышь и палец на схеме: перетаскивание, колесо, клик по пустому месту
 * (выбор точки новой заявки) и кнопки масштаба. Возвращает функцию,
 * снимающую слушателей с окна. */
export function attachSchemeInput(container, viewport, draw, fit, onPick) {
  const { view } = viewport;
  // Перетаскивание слушаем на окне, а не через захват указателя на
  // контейнере: захват перенаправляет события на контейнер, и клик
  // по метке до неё уже не доходит.
  let drag = null;
  let dragged = false;

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
  const zoom = (factor, px, py) => {
    viewport.zoomAt(factor, px, py);
    draw();
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
    zoom(event.deltaY < 0 ? 1.2 : 1 / 1.2,
         event.clientX - rect.left, event.clientY - rect.top);
  }, { passive: false });

  container.addEventListener('click', (event) => {
    if (dragged || event.target.closest('.scheme-controls')) return;
    if (event.target.closest('.scheme-pin')) return;
    const rect = container.getBoundingClientRect();
    const at = viewport.toLatLon(event.clientX - rect.left, event.clientY - rect.top);
    onPick(at.lat, at.lon);
  });

  container.querySelector('.scheme-controls').onclick = (event) => {
    const act = event.target.dataset.act;
    if (act === 'in') zoom(1.4);
    if (act === 'out') zoom(1 / 1.4);
    if (act === 'fit') fit();
  };

  return onUp;
}
