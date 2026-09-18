import { CheckCircle } from '@phosphor-icons/react';

import type { Order, Unassigned } from '../../api/types';

interface Props {
  items: Unassigned[];
  orders: Order[];
  selected: string | null;
  onSelect: (orderId: string) => void;
}

/** Заявки без исполнителя.

Причина показывается словами: код отказа ничего не говорит диспетчеру и не
подсказывает действия.
*/
export function UnassignedList({ items, orders, selected, onSelect }: Props) {
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

  return (
    <ul>
      {items.map((item) => {
        const order = byId.get(item.order_id);
        const active = selected === item.order_id;
        return (
          <li key={item.order_id} className="border-b border-line last:border-0">
            <button
              type="button"
              onClick={() => onSelect(item.order_id)}
              aria-current={active || undefined}
              className={
                'flex w-full min-w-0 flex-col gap-0.5 border-l-2 px-3 py-2 text-left ' +
                'transition-colors duration-[120ms] ' +
                (active
                  ? 'border-danger bg-danger-soft'
                  : 'border-transparent hover:border-line-2 hover:bg-raised')
              }
            >
              <span className="flex min-w-0 items-baseline gap-2">
                <span className="text-[13px] font-medium tnum">№ {item.order_id}</span>
                {order ? (
                  <>
                    <span className="text-[12px] text-ink-3 tnum">
                      {order.window_start}–{order.window_end}
                    </span>
                    <span className="truncate text-[12px] text-ink-3">{order.district}</span>
                  </>
                ) : null}
              </span>
              <span className="text-[12px] text-ink-2">{item.reason_text}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
