import { useEffect, useRef, useState } from 'react';

import type { PlanPayload } from '../../api/types';
import type { DispatcherMap } from './map';
import { createDispatcherMap } from './map.js';
import { buildMapModel } from './model';
import './map.css';

interface Props {
  plan: PlanPayload | undefined;
  hiddenCrews: Set<string>;
  focusCrew: string | null;
  selected: string | null;
  apiKey: string;
  theme: string;
  onSelect: (orderId: string) => void;
}

/** Карта плана.

Грузится отдельно от плана и до готовности показывает свою схему: раньше
недоступный ключ задерживал весь запуск, и человек до сорока секунд смотрел
в пустоту.
*/
export function MapView({
  plan,
  hiddenCrews,
  focusCrew,
  selected,
  apiKey,
  theme,
  onSelect,
}: Props) {
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<DispatcherMap | null>(null);
  // Схема подписывает себя сама, поэтому называем источник только тогда,
  // когда работают Яндекс Карты: две подписи наезжали друг на друга.
  const [yandex, setYandex] = useState(false);
  // Карта готова позже плана. Без этого признака первый план остался бы
  // неотрисованным: эффект отрисовки отработал бы на пустой ссылке.
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let alive = true;
    const node = box.current;
    if (!node) return;

    createDispatcherMap(node, {
      apiKey: apiKey || null,
      theme,
      onSelectOrder: onSelect,
    }).then((created) => {
      if (!alive) {
        created.destroy();
        return;
      }
      map.current = created;
      setReady(true);
      setYandex(created.kind === 'yandex');
    });

    return () => {
      alive = false;
      map.current?.destroy();
      map.current = null;
      setReady(false);
    };
    // Карта создаётся один раз: пересоздание на каждый расчёт теряло бы
    // выбранный масштаб и положение.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!map.current || !plan) return;
    map.current.render(buildMapModel(plan, hiddenCrews, focusCrew));
  }, [plan, hiddenCrews, focusCrew, ready]);

  // Контейнер меняет размер не только вместе с окном: раскрытая полоса
  // события отнимает высоту. Перерисовываем по тем же данным, но масштаб не
  // трогаем: вписывание заново сжимало схему в комок и скакало с 2 км на 10.
  useEffect(() => {
    const node = box.current;
    if (!node || !ready || !plan) return;
    const watch = new ResizeObserver(() => {
      map.current?.render(buildMapModel(plan, hiddenCrews, focusCrew));
    });
    watch.observe(node);
    return () => watch.disconnect();
  }, [ready, plan, hiddenCrews, focusCrew]);

  useEffect(() => {
    if (!map.current) return;
    map.current.focusOrder(selected);
  }, [selected, ready]);

  useEffect(() => {
    if (!map.current) return;
    map.current.setTheme(theme);
  }, [theme, ready]);

  return (
    <section
      data-testid="map"
      className="relative min-h-[320px] w-full min-w-0 overflow-hidden rounded-lg border border-line bg-panel"
    >
      <div ref={box} className="absolute inset-0" />
      {yandex ? (
        <span className="absolute right-3 top-3 rounded-md border border-line bg-panel/90 px-2 py-1 text-[11px] text-ink-3">
          Карта: Яндекс Карты
        </span>
      ) : null}
    </section>
  );
}
