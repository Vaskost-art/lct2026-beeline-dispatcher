import { CheckCircle } from '@phosphor-icons/react';

import type { Order, Unassigned } from '../../api/types';
import { plural } from '../../text';

interface Props {
  items: Unassigned[];
  orders: Order[];
  selected: string | null;
  onSelect: (orderId: string) => void;
  /** Разбор нехватки людей: туда ведёт совет «добавить бригаду». */
  onShortfall: () => void;
}

/** Что делать с отказом. Причина называет препятствие, а диспетчеру нужно
    действие: этот список переводит одно в другое. */
const WHAT_TO_DO: { match: RegExp; text: string }[] = [
  { match: /транспорт/i, text: 'Добавить бригаду с автомобилем или снять требование транспорта' },
  { match: /навык/i, text: 'Добавить бригаду с нужным навыком' },
  { match: /окн/i, text: 'Согласовать с клиентом другое окно или добавить бригаду' },
  { match: /смен|врем/i, text: 'Продлить смену или передать заявку на завтра' },
];

function advice(reason: string): string {
  return (
    WHAT_TO_DO.find((rule) => rule.match.test(reason))?.text ??
    'Добавить бригаду или перенести заявку'
  );
}

/** Заявки без исполнителя, сгруппированные по причине.

Одинаковая причина у пяти заявок подряд превращает список в стену текста, в
которой не видно ни одной заявки. Причина называется один раз, а рядом с ней
стоит действие: диспетчер по этому экрану работает, а не читает.
*/
export function UnassignedList({ items, orders, selected, onSelect, onShortfall }: Props) {
  const byId = new Map(orders.map((order) => [order.id, order]));

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 px-6 py-10 text-center">
        <CheckCircle size={24} weight="duotone" aria-hidden className="text-ok" />
        <p className="text-[13px] font-medium">Все заявки разошлись по бригадам</p>
        <p className="max-w-[46ch] text-[12px] text-ink-3">
          Здесь появятся заявки, которые не помещаются в смену: с причиной и подсказкой,
          чем это чинится.
        </p>
      </div>
    );
  }

  const groups = new Map<string, Unassigned[]>();
  for (const item of items) {
    const bucket = groups.get(item.reason_text) ?? [];
    bucket.push(item);
    groups.set(item.reason_text, bucket);
  }

  return (
    <div className="flex flex-col">
      {[...groups.entries()].map(([reason, group]) => (
        <section key={reason} className="border-b border-line last:border-0">
          <header className="flex flex-col gap-1 bg-raised/50 px-3 py-2">
            <span className="flex items-baseline gap-2">
              <span className="rounded-sm bg-danger-soft px-1.5 py-0.5 text-[11px] font-semibold text-danger tnum">
                {group.length}
              </span>
              <span className="min-w-0 text-[12px] text-ink-2">{reason}</span>
            </span>
            <button
              type="button"
              onClick={onShortfall}
              className="w-fit rounded-md border border-line bg-panel px-2 py-1 text-[12px]
                         font-medium text-ink transition-colors duration-[120ms] hover:border-accent"
            >
              {advice(reason)}
            </button>
          </header>

          <ul>
            {group.map((item) => {
              const order = byId.get(item.order_id);
              const active = selected === item.order_id;
              return (
                <li key={item.order_id}>
                  <button
                    type="button"
                    onClick={() => onSelect(item.order_id)}
                    aria-current={active || undefined}
                    className={
                      'grid h-9 w-full grid-cols-[minmax(0,1fr)_92px_minmax(0,110px)] items-center gap-2 ' +
                      'border-l-2 px-3 text-left transition-colors duration-[120ms] ' +
                      (active
                        ? 'border-danger bg-danger-soft'
                        : 'border-transparent hover:border-line-2 hover:bg-raised')
                    }
                  >
                    <span className="truncate text-[13px] font-medium tnum">№ {item.order_id}</span>
                    <span className="text-[12px] text-ink-3 tnum">
                      {order ? `${order.window_start}–${order.window_end}` : ''}
                    </span>
                    <span className="truncate text-right text-[12px] text-ink-3">
                      {order?.district ?? ''}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      ))}

      <p className="px-3 py-2 text-[12px] text-ink-3">
        Всего {items.length} {plural(items.length, 'заявка', 'заявки', 'заявок')} без
        исполнителя. Нажмите на любую, чтобы увидеть, кто мог её взять.
      </p>
    </div>
  );
}
