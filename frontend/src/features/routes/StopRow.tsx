import type { Order, Stop } from '../../api/types';
import { priorityMark } from '../../priority';

interface Props {
  index: number;
  stop: Stop;
  order: Order | undefined;
  /** Что отмечено по заявке: «Отправлено» не показываем, это обычное дело. */
  status: string;
  selected: boolean;
  onSelect: (orderId: string) => void;
}

/** Как показывать отметку хода работ. Цвет означает исход, а не событие:
зелёный - сделано, серый - отменено, синий - идёт сейчас. */
const STATUS_TONE: Record<string, string> = {
  'В пути': 'bg-accent-soft text-accent',
  Выполняется: 'bg-accent-soft text-accent',
  Завершено: 'bg-ok-soft text-ok',
  Отменена: 'bg-raised text-ink-3 line-through',
};

/** Одна остановка маршрута: время, адрес, оборудование.

Слева рельс дня: точка визита и линия дороги до следующего. Так видно
плотность смены, а не только строки текста.

Пустых мест здесь нет: прочерк читается как ноль, а срочность отмечается
меткой. Выбор показывается полосой слева, а не рамкой: рамка сдвигает
содержимое и строка дёргается.
*/
/** Способы, которые не меняются от визита к визиту. */
const SINGLE_MODE = new Set(['на машине', 'на велосипеде']);

export function StopRow({ index, stop, order, status, selected, onSelect }: Props) {
  const tone = STATUS_TONE[status];
  const mark = priorityMark(order?.priority);

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
          {/* Строка переносится, а не сжимается: на узкой колонке метка
              «подключение» наезжала на время в пути. */}
          <span className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <span className="shrink-0 whitespace-nowrap text-[12px] font-semibold tnum">
              {stop.start}
              <span className="text-ink-3">–{stop.end}</span>
            </span>
            {tone ? (
              <span className={'shrink-0 rounded-sm px-1 text-[10px] font-medium ' + tone}>
                {status.toLowerCase()}
              </span>
            ) : null}
            {mark ? (
              <span
                className={
                  'shrink-0 rounded-sm px-1 text-[10px] font-semibold uppercase ' +
                  'tracking-[0.04em] ' + mark.tone
                }
              >
                {mark.text}
              </span>
            ) : null}
            <span className="min-w-0 truncate text-[12px] text-ink-3">
              {order ? order.district : 'район неизвестен'}
            </span>
          </span>

          {/* Адрес переносится на вторую строку: по нему звонят, обрезать нельзя. */}
          <span className="line-clamp-2 block text-[12px] text-ink-2">
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

        <span className="shrink-0 pt-0.5 text-right text-[11px] text-ink-3 tnum">
          <span className="block">{stop.travel_min} мин в пути</span>
          {/* У машины и велосипеда способ один, и подпись в каждой строке
              была шумом: транспорт бригады и так назван в её строке. */}
          {stop.travel_mode && !SINGLE_MODE.has(stop.travel_mode) ? (
            <span className="block text-ink-3">{stop.travel_mode}</span>
          ) : null}
          {stop.wait_min > 0 ? (
            <span className="block text-warn">ждём {stop.wait_min} мин</span>
          ) : null}
        </span>
      </button>
    </li>
  );
}
