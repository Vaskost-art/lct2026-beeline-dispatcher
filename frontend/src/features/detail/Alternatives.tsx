import type { Alternative } from '../../api/types';
import { plural } from '../../text';

interface Props {
  items: Alternative[];
  total?: number;
  /** Свернуть разбор. Для назначенной заявки он справочный: постановщик
   * просил краткое обоснование, а развёрнутое - прежде всего там, где
   * исполнителя не нашлось. */
  collapsed?: boolean;
}

/** Кто ещё мог взять заявку и почему не взял.

Это ответ на главный вопрос диспетчера к машине: «почему именно эта бригада».
Отказы с одинаковой причиной сводятся в строку: восемь одинаковых карточек
«нет навыка» не говорят больше, чем одна.
*/
export function Alternatives({ items, total, collapsed = false }: Props) {
  if (items.length === 0) return null;

  const could = items.filter((item) => item.possible);
  const refused = items.filter((item) => !item.possible);

  const byReason = new Map<string, string[]>();
  for (const item of refused) {
    const bucket = byReason.get(item.reason) ?? [];
    bucket.push(item.engineer_id);
    byReason.set(item.reason, bucket);
  }

  const body = (
    <>
      {could.length > 0 ? (
        <ul className="mb-2 flex flex-col gap-1">
          {could.map((item) => (
            <li
              key={item.engineer_id}
              className="flex min-w-0 items-baseline gap-2 rounded-md border border-line px-2 py-1.5"
            >
              <span className="min-w-0 flex-1 truncate text-[12px] font-medium">
                {item.engineer_id}
              </span>
              {item.extra_km === undefined ? null : (
                <span className="shrink-0 text-[12px] text-ink-2 tnum">
                  +{item.extra_km.toFixed(1)} <span className="text-ink-3">км</span>
                </span>
              )}
            </li>
          ))}
        </ul>
      ) : null}

      <ul className="flex flex-col gap-1">
        {[...byReason.entries()].map(([reason, crews]) => (
          <li key={reason} className="flex min-w-0 flex-col gap-0.5 rounded-md bg-raised/60 px-2 py-1.5">
            <span className="text-[12px] text-ink-2">{reason}</span>
            <span className="text-[11px] text-ink-3">
              {crews.length} {plural(crews.length, 'бригада', 'бригады', 'бригад')}:{' '}
              {crews.slice(0, 3).join(', ')}
              {crews.length > 3 ? ` и ещё ${crews.length - 3}` : ''}
            </span>
          </li>
        ))}
      </ul>
    </>
  );

  const title = (
    <>
      Кто ещё мог взять
      {total ? <span className="ml-1 font-normal text-ink-3">разобрано {total}</span> : null}
    </>
  );

  if (collapsed) {
    return (
      <details className="mt-4">
        <summary className="cursor-pointer text-[13px] font-semibold">{title}</summary>
        <div className="mt-1.5">{body}</div>
      </details>
    );
  }

  return (
    <section className="mt-4">
      <h3 className="mb-1.5 text-[13px] font-semibold">{title}</h3>
      {body}
    </section>
  );
}
