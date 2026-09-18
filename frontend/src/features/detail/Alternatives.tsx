import type { Alternative } from '../../api/types';

interface Props {
  items: Alternative[];
  total?: number;
}

/** Кто ещё мог взять заявку и почему не взял.

Это ответ на главный вопрос диспетчера к машине: «почему именно эта бригада».
Без него план приходится принимать на веру.
*/
export function Alternatives({ items, total }: Props) {
  if (items.length === 0) return null;

  return (
    <section className="mt-4">
      <h3 className="eyebrow mb-1.5">
        Кто ещё мог взять{total ? ` · разобрано ${total}` : ''}
      </h3>
      <ul className="flex flex-col gap-1">
        {items.map((item) => (
          <li
            key={item.engineer_id}
            className="flex min-w-0 flex-col gap-0.5 rounded-md border border-line px-2 py-1.5"
          >
            <span className="flex min-w-0 items-baseline justify-between gap-2">
              <span className="truncate text-[12px] font-medium">{item.engineer_id}</span>
              {item.possible && item.extra_km !== undefined ? (
                <span className="shrink-0 text-[11px] text-ink-3 tnum">
                  +{item.extra_km.toFixed(1)} км
                </span>
              ) : (
                <span className="shrink-0 text-[11px] text-ink-4">не может</span>
              )}
            </span>
            <span className="text-[12px] text-ink-2">{item.reason}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
