import { CaretRight } from '@phosphor-icons/react';
import { useState } from 'react';

import type { Order, Route } from '../../api/types';
import { crewColor } from '../map/model';
import { plural } from '../../text';
import { StopRow } from './StopRow';

interface Props {
  route: Route;
  orders: Order[];
  index: number;
  selected: string | null;
  onSelect: (orderId: string) => void;
}

/** Маршрут одной бригады: свёрнут до сводки, раскрывается в остановки.

Цвет слева тот же, что у маршрута на карте: список и карта должны читаться
как одно целое, иначе диспетчер сверяет их глазами вручную.
*/
export function RouteRow({ route, orders, index, selected, onSelect }: Props) {
  const [open, setOpen] = useState(false);
  const byId = new Map(orders.map((order) => [order.id, order]));
  const items = route.stops.reduce((total, stop) => {
    const order = byId.get(stop.order_id);
    return total + (order ? order.equipment.length : 0);
  }, 0);
  const hasSelected = route.stops.some((stop) => stop.order_id === selected);

  return (
    <li className="border-b border-line last:border-0">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className={
          'flex h-9 w-full min-w-0 items-center gap-2 pl-2 pr-3 text-left transition-colors duration-[120ms] ' +
          (hasSelected && !open ? 'bg-accent-soft' : 'hover:bg-raised')
        }
      >
        <CaretRight
          size={12}
          weight="bold"
          aria-hidden
          className={
            'shrink-0 text-ink-4 transition-transform duration-[120ms] ' + (open ? 'rotate-90' : '')
          }
        />
        <span
          aria-hidden
          className="size-2 shrink-0 rounded-full"
          style={{ background: crewColor(index) }}
        />
        <span className="min-w-0 flex-1 truncate text-[13px] font-medium">{route.engineer_id}</span>
        <span className="shrink-0 text-[12px] text-ink-3 tnum">
          {route.stops.length} {plural(route.stops.length, 'заявка', 'заявки', 'заявок')}
        </span>
        <span className="w-16 shrink-0 text-right text-[12px] text-ink-3 tnum">
          {route.total_km.toFixed(1)} <span className="text-ink-4">км</span>
        </span>
        <span className="w-14 shrink-0 text-right text-[12px] text-ink-3 tnum">
          {items > 0 ? (
            <>
              {items} <span className="text-ink-4">шт</span>
            </>
          ) : (
            <span className="text-ink-4">без груза</span>
          )}
        </span>
      </button>

      {open ? (
        <ul className="bg-raised/45 pb-1">
          {route.stops.map((stop, position) => (
            <StopRow
              key={stop.order_id}
              index={position + 1}
              stop={stop}
              order={byId.get(stop.order_id)}
              selected={selected === stop.order_id}
              onSelect={onSelect}
            />
          ))}
        </ul>
      ) : null}
    </li>
  );
}
