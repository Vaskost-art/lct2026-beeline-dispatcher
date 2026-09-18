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
«обычная» это настоящее значение. Выбор отмечается полосой слева, а не
рамкой: рамка сдвигает содержимое и строка дёргается.
*/
export function StopRow({ index, stop, order, selected, onSelect }: Props) {
  const urgent = order?.priority.toLowerCase().startsWith('срочн') ?? false;

  return (
    <li>
      <button
        type="button"
        onClick={() => onSelect(stop.order_id)}
        aria-current={selected || undefined}
        className={
          'flex w-full min-w-0 items-start gap-3 border-l-2 py-1.5 pl-4 pr-3 text-left ' +
          'transition-colors duration-[120ms] ' +
          (selected
            ? 'border-accent bg-accent-soft'
            : 'border-transparent hover:border-line-2 hover:bg-panel')
        }
      >
        <span className="w-4 shrink-0 pt-0.5 text-right text-[11px] text-ink-4 tnum">{index}</span>

        <span className="min-w-0 flex-1">
          <span className="flex min-w-0 items-baseline gap-2">
            <span className="text-[12px] font-semibold tnum">
              {stop.start}
              <span className="text-ink-4">–{stop.end}</span>
            </span>
            {urgent ? (
              <span className="rounded-sm bg-danger-soft px-1 text-[10px] font-semibold uppercase tracking-[0.04em] text-danger">
                срочная
              </span>
            ) : null}
            <span className="truncate text-[12px] text-ink-3">
              {order ? order.district : 'район неизвестен'}
            </span>
          </span>

          <span className="block truncate text-[12px] text-ink-2">
            {order ? order.address : 'адрес неизвестен'}
          </span>

          {order && order.equipment.length > 0 ? (
            <span className="mt-0.5 flex flex-wrap gap-1">
              {order.equipment.map((item) => (
                <span
                  key={item}
                  className="rounded-sm border border-line bg-panel px-1 text-[10px] text-ink-2"
                >
                  {item}
                </span>
              ))}
            </span>
          ) : null}
        </span>

        <span className="shrink-0 pt-0.5 text-right text-[11px] text-ink-4 tnum">
          {stop.travel_min} мин
          {stop.wait_min > 0 ? <span className="block">ждём {stop.wait_min}</span> : null}
        </span>
      </button>
    </li>
  );
}
