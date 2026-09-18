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
    return <p className="p-3 text-muted">Все заявки разошлись по бригадам.</p>;
  }

  return (
    <ul>
      {items.map((item) => {
        const order = byId.get(item.order_id);
        return (
          <li key={item.order_id} className="border-b border-line">
            <button
              type="button"
              onClick={() => onSelect(item.order_id)}
              aria-current={selected === item.order_id || undefined}
              className={
                'flex w-full min-w-0 flex-col gap-0.5 px-3 py-2 text-left text-sm ' +
                (selected === item.order_id ? 'bg-bg' : 'hover:bg-bg')
              }
            >
              <span className="flex min-w-0 items-center gap-2">
                <span className="font-medium">Заявка {item.order_id}</span>
                {order ? (
                  <span className="truncate text-muted">
                    {order.window_start}–{order.window_end} · {order.district}
                  </span>
                ) : null}
              </span>
              <span className="text-muted">{item.reason_text}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
