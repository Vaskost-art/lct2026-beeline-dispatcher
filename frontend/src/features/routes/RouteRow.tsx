import { CaretRight } from '@phosphor-icons/react';

import type { Order, Route } from '../../api/types';

/** Короткое имя транспорта: полное не помещается в колонку и обрезается
    многоточием ровно там, где начинается смысл. Пешая бригада и бригада на
    транспорте ходят одинаково, быстрейшим из двух способов: подпись «пешком»
    при двадцати пяти километрах за день читалась как ошибка. */
const SHORT_VEHICLE: Record<string, string> = {
  Автомобиль: 'авто',
  'Общественный транспорт': 'без машины',
  Велосипед: 'велосипед',
  Пешеход: 'без машины',
};
import { crewColor } from '../map/model';
import { StopRow } from './StopRow';
import { decimal } from '../../text';

interface Props {
  route: Route;
  orders: Order[];
  /** Чем бригада ездит: транспорт различает людей лучше номера. */
  vehicle: string | undefined;
  index: number;
  open: boolean;
  focused: boolean;
  selected: string | null;
  /** Сколько устройств бригада берёт утром: та же ведомость, что в итоге. */
  load: number;
  /** Отметки хода работ по заявкам этого участка. */
  statuses?: Record<string, string>;
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
  load,
  vehicle,
  index,
  open,
  focused,
  statuses,
  selected,
  onToggle,
  onSelect,
}: Props) {
  const byId = new Map(orders.map((order) => [order.id, order]));
  const last = route.stops.at(-1);
  // Простой в строках визитов виден поштучно, а решение принимается по
  // сумме: три ожидания по часу это несделанная заявка.
  const idle = route.stops.reduce((sum, stop) => sum + stop.wait_min, 0);

  return (
    <li className="border-b border-line last:border-0">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className={
          'grid h-9 w-full grid-cols-[14px_10px_minmax(0,1fr)_48px_56px] lg:grid-cols-[14px_10px_minmax(0,1fr)_56px_64px_52px] items-center gap-2 ' +
          'pl-2 pr-3 text-left transition-colors duration-[120ms] ' +
          (focused ? 'bg-raised' : 'hover:bg-raised')
        }
      >
        <CaretRight
          size={12}
          weight="bold"
          aria-hidden
          className={'text-ink-3 transition-transform duration-[120ms] ' + (open ? 'rotate-90' : '')}
        />
        <span
          aria-hidden
          className="size-2.5 rounded-full"
          style={{ background: crewColor(index) }}
        />
        <span className="flex min-w-0 items-baseline gap-2">
          <span className="shrink-0 text-[13px] font-medium">{route.engineer_id}</span>
          {vehicle ? (
            <span className="hidden min-w-0 truncate text-[11px] text-ink-3 sm:inline">
              {SHORT_VEHICLE[vehicle] ?? vehicle}
            </span>
          ) : null}
        </span>
        <span className="text-right text-[12px] tnum">{route.stops.length}</span>
        <span className="text-right text-[12px] tnum">{decimal(route.total_km)}</span>
        <span className="hidden text-right text-[12px] tnum lg:block">
          {load > 0 ? load : <span className="text-ink-3">0</span>}
        </span>
      </button>

      {open ? (
        <div className="bg-raised/40 pb-1">
          {last ? (
            <p className="px-4 pb-1 pt-1.5 text-[11px] text-ink-3">
              Смена занята до <span className="tnum font-medium">{last.end}</span> ·{' '}
              {route.total_travel_min} мин в дороге
              {/* Простой в строках визитов виден поштучно, а решение принимается
                  по сумме: три ожидания по часу это несделанная заявка. */}
              {idle > 0 ? (
                <span className="whitespace-nowrap">
                  {' · '}
                  <span className="font-medium text-warn tnum">{idle} мин</span> ждём окон
                </span>
              ) : null}
            </p>
          ) : null}
          <ul>
            {route.stops.map((stop, position) => (
              <StopRow
                key={stop.order_id}
                index={position + 1}
                stop={stop}
                order={byId.get(stop.order_id)}
                status={statuses?.[stop.order_id] ?? 'Отправлено'}
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
