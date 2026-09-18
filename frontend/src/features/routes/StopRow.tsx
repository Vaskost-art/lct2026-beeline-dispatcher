import type { Order, Stop } from '../../api/types';

interface Props {
  index: number;
  stop: Stop;
  order: Order | undefined;
  selected: boolean;
  onSelect: (orderId: string) => void;
}

/** Одна остановка маршрута: время, адрес, оборудование.

Слева рельс дня: точка визита и линия дороги до следующего. Так видно
плотность смены, а не только строки текста.

Пустых мест здесь нет: прочерк читается как ноль, а срочность отмечается
меткой. Выбор показывается полосой слева, а не рамкой: рамка сдвигает
содержимое и строка дёргается.
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
          'flex w-full min-w-0 items-stretch gap-3 border-l-2 py-1.5 pl-3 pr-3 text-left ' +
          'transition-colors duration-[120ms] ' +
          (selected
            ? 'border-accent bg-raised'
            : 'border-transparent hover:border-line-2 hover:bg-panel')
        }
      >
        <span aria-hidden className="relative flex w-4 shrink-0 justify-center pt-1">
          <span className="absolute inset-y-0 w-px bg-line-2" />
          <span className="relative z-10 flex size-4 items-center justify-center rounded-full border border-line-2 bg-panel text-[9px] text-ink-3 tnum">
            {index}
          </span>
        </span>

        <span className="min-w-0 flex-1 pb-0.5">
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
            <span className="mt-1 flex flex-wrap gap-1">
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
          <span className="block">{stop.travel_min} мин в пути</span>
          {stop.wait_min > 0 ? (
            <span className="block text-warn">ждём {stop.wait_min} мин</span>
          ) : null}
        </span>
      </button>
    </li>
  );
}
