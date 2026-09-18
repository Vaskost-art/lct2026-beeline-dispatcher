import type { Order, Stop } from '../../api/types';

interface Props {
  index: number;
  stop: Stop;
  order: Order | undefined;
  selected: boolean;
  onSelect: (orderId: string) => void;
}

/** Одна остановка маршрута: время, адрес, оборудование.

Пустых мест здесь нет: прочерк в колонке приоритета читается как ноль, а
«обычная» это настоящее значение.
*/
export function StopRow({ index, stop, order, selected, onSelect }: Props) {
  return (
    <li>
      <button
        type="button"
        onClick={() => onSelect(stop.order_id)}
        aria-current={selected || undefined}
        className={
          'flex w-full min-w-0 flex-col gap-0.5 border-l-2 px-3 py-2 text-left text-sm ' +
          (selected ? 'border-accent bg-bg' : 'border-transparent hover:bg-bg')
        }
      >
        <span className="flex min-w-0 items-center gap-2">
          <span className="text-muted">{index}.</span>
          <span className="font-medium">
            {stop.start}–{stop.end}
          </span>
          <span className="truncate text-muted">
            {order ? order.district : 'район неизвестен'}
          </span>
        </span>
        <span className="truncate text-muted">{order ? order.address : 'адрес неизвестен'}</span>
        <span className="flex flex-wrap gap-x-3 text-xs text-muted">
          <span>{order ? order.priority.toLowerCase() : 'приоритет неизвестен'}</span>
          <span>в пути {stop.travel_min} мин</span>
          {stop.wait_min > 0 ? <span>ожидание {stop.wait_min} мин</span> : null}
          {order && order.equipment.length > 0 ? (
            <span className="text-text">везём: {order.equipment.join(', ')}</span>
          ) : null}
        </span>
      </button>
    </li>
  );
}
