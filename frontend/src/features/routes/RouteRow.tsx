import { CaretDown, CaretRight } from '@phosphor-icons/react';
import { useState } from 'react';

import type { Order, Route } from '../../api/types';
import { plural } from '../../text';
import { StopRow } from './StopRow';

interface Props {
  route: Route;
  orders: Order[];
  selected: string | null;
  onSelect: (orderId: string) => void;
}

/** Маршрут одной бригады: свёрнут до сводки, раскрывается в остановки. */
export function RouteRow({ route, orders, selected, onSelect }: Props) {
  const [open, setOpen] = useState(false);
  const byId = new Map(orders.map((order) => [order.id, order]));
  const items = route.stops.reduce((total, stop) => {
    const order = byId.get(stop.order_id);
    return total + (order ? order.equipment.length : 0);
  }, 0);

  return (
    <li className="border-b border-line">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full min-w-0 items-center gap-2 px-3 py-2 text-left hover:bg-bg"
      >
        {open ? <CaretDown size={14} /> : <CaretRight size={14} />}
        <span className="min-w-0 flex-1 truncate font-medium">{route.engineer_id}</span>
        <span className="shrink-0 text-xs text-muted">
          {route.stops.length} {plural(route.stops.length, 'заявка', 'заявки', 'заявок')} ·{' '}
          {route.total_km.toFixed(1)} км
          {items > 0 ? ` · везём ${items}` : ''}
        </span>
      </button>

      {open ? (
        <ul>
          {route.stops.map((stop, index) => (
            <StopRow
              key={stop.order_id}
              index={index + 1}
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
