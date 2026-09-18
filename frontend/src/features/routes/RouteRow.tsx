import { CaretRight } from '@phosphor-icons/react';

import type { Order, Route } from '../../api/types';

/** Короткое имя транспорта: полное не помещается в колонку и обрезается
    многоточием ровно там, где начинается смысл. */
const SHORT_VEHICLE: Record<string, string> = {
  Автомобиль: 'авто',
  'Общественный транспорт': 'транспорт',
  Велосипед: 'велосипед',
  Пешеход: 'пешком',
};
import { crewColor } from '../map/model';
import { StopRow } from './StopRow';

interface Props {
  route: Route;
  orders: Order[];
  /** Чем бригада ездит: транспорт различает людей лучше номера. */
  vehicle: string | undefined;
  index: number;
  open: boolean;
  focused: boolean;
  selected: string | null;
  onToggle: () => void;
  onSelect: (orderId: string) => void;
}

/** Строка бригады: сводка в колонках, раскрывается в остановки.

Цвет слева тот же, что у маршрута на карте: список и карта должны читаться
как одно целое, иначе диспетчер сверяет их глазами вручную.
*/
export function RouteRow({
  route,
  orders,
  vehicle,
  index,
  open,
  focused,
  selected,
  onToggle,
  onSelect,
}: Props) {
  const byId = new Map(orders.map((order) => [order.id, order]));
  const items = route.stops.reduce((total, stop) => {
    const order = byId.get(stop.order_id);
    return total + (order ? order.equipment.length : 0);
  }, 0);
  const last = route.stops.at(-1);

  return (
    <li className="border-b border-line last:border-0">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className={
          'grid h-9 w-full grid-cols-[14px_10px_minmax(0,1fr)_56px_64px_52px] items-center gap-2 ' +
          'pl-2 pr-3 text-left transition-colors duration-[120ms] ' +
          (focused ? 'bg-accent-soft' : 'hover:bg-raised')
        }
      >
        <CaretRight
          size={12}
          weight="bold"
          aria-hidden
          className={'text-ink-4 transition-transform duration-[120ms] ' + (open ? 'rotate-90' : '')}
        />
        <span
          aria-hidden
          className="size-2.5 rounded-full"
          style={{ background: crewColor(index) }}
        />
        <span className="flex min-w-0 items-baseline gap-2">
          <span className="shrink-0 text-[13px] font-medium">{route.engineer_id}</span>
          {vehicle ? (
            <span className="hidden min-w-0 truncate text-[11px] text-ink-4 sm:inline">
              {SHORT_VEHICLE[vehicle] ?? vehicle}
            </span>
          ) : null}
        </span>
        <span className="text-right text-[12px] tnum">{route.stops.length}</span>
        <span className="text-right text-[12px] tnum">{route.total_km.toFixed(1)}</span>
        <span className="text-right text-[12px] tnum">
          {items > 0 ? items : <span className="text-ink-4">0</span>}
        </span>
      </button>

      {open ? (
        <div className="bg-raised/40 pb-1">
          {last ? (
            <p className="px-4 pb-1 pt-1.5 text-[11px] text-ink-3">
              Смена занята до <span className="tnum font-medium">{last.end}</span> ·{' '}
              {route.total_travel_min} мин в дороге
            </p>
          ) : null}
          <ul>
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
        </div>
      ) : null}
    </li>
  );
}
