import { useEffect, useRef, useState } from 'react';

import type { PlanPayload } from '../../api/types';
import type { DispatcherMap } from './map';
import { createDispatcherMap } from './map.js';
import { buildMapModel } from './model';
import './map.css';

interface Props {
  plan: PlanPayload | undefined;
  hiddenCrews: Set<string>;
  selected: string | null;
  apiKey: string;
  theme: string;
  onSelect: (orderId: string) => void;
}

const SCHEME_SOURCE = 'Карта: собственная схема, подложки нет';

/** Карта плана.

Грузится отдельно от плана и до готовности показывает свою схему: раньше
недоступный ключ задерживал весь запуск, и человек до сорока секунд смотрел
в пустоту.
*/
export function MapView({ plan, hiddenCrews, selected, apiKey, theme, onSelect }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<DispatcherMap | null>(null);
  const [source, setSource] = useState('Карта загружается');
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
      onFallback: () => {
        // Ключ не задан или сервис не ответил: говорим прямо, а не делаем
        // вид, что схема и была задумана.
        setSource(SCHEME_SOURCE);
      },
      onSelectOrder: onSelect,
    }).then((created) => {
      if (!alive) {
        created.destroy();
        return;
      }
      map.current = created;
      setReady(true);
      setSource(created.kind === 'yandex' ? 'Карта: Яндекс Карты' : SCHEME_SOURCE);
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
    map.current.render(buildMapModel(plan, hiddenCrews));
  }, [plan, hiddenCrews, ready]);

  useEffect(() => {
    if (!map.current) return;
    map.current.focusOrder(selected);
  }, [selected, ready]);

  useEffect(() => {
    if (!map.current) return;
    map.current.setTheme(theme);
  }, [theme, ready]);

  return (
    <div className="relative min-h-[320px] min-w-0 overflow-hidden rounded-lg border border-line bg-panel">
      <div ref={box} className="absolute inset-0" />
      <span className="absolute bottom-2 right-2 rounded bg-panel/90 px-2 py-1 text-xs text-muted">
        {source}
      </span>
    </div>
  );
}
