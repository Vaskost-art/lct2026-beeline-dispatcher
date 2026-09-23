import { useState } from 'react';

import { useOrderStatus } from '../../api/queries';
import type { ApiError } from '../../api/client';
import { Button } from '../../components/Button';

/** Состояния заявки в порядке смены: наряд, дорога, работа, закрытие. */
const MARKS = ['Отправлено', 'В пути', 'Выполняется', 'Завершено', 'Отменена'];

/** Отметки, после которых заявка уходит из планирования: их переспрашиваем. */
const CLOSING: Record<string, string> = {
  Завершено: 'Заявка закроется и больше не попадёт в пересчёт дня.',
  Отменена: 'Заявка снимется с маршрута и больше не попадёт в пересчёт дня.',
};

interface Props {
  region: string;
  orderId: string;
  status: string;
}

/** Ход работ по заявке со слов бригады.

Закрывающая отметка стоит вплотную к рабочим, и случайное касание снимало
заявку с маршрута. Поэтому «Завершено» и «Отменена» подтверждаются.
*/
export function StatusMarks({ region, orderId, status }: Props) {
  const mark = useOrderStatus();
  const [asking, setAsking] = useState<string | null>(null);

  const put = (name: string) => {
    setAsking(null);
    mark.mutate({ region, order_id: orderId, status: name });
  };

  return (
    <div className="mb-3 border-b border-line pb-3">
      <span className="text-[12px] font-medium text-ink-3">Ход работ</span>
      <div role="group" aria-label="Ход работ" className="mt-1 flex flex-wrap gap-1">
        {MARKS.map((name) => (
          <button
            key={name}
            type="button"
            aria-pressed={status === name}
            disabled={mark.isPending}
            onClick={() => {
              if (status === name) return;
              if (CLOSING[name]) setAsking(name);
              else put(name);
            }}
            className={
              'min-h-6 rounded-md border px-2 py-1 text-[12px] transition-colors ' +
              (status === name
                ? 'border-accent bg-accent-soft font-medium text-ink'
                : 'border-line bg-panel text-ink-2 hover:bg-raised')
            }
          >
            {name}
          </button>
        ))}
      </div>

      {asking ? (
        <div className="mt-2 rounded-md border border-line bg-raised px-2 py-2 text-[12px]">
          <p className="text-ink">
            Отметить «{asking}»? {CLOSING[asking]} Вернуть можно шагом назад.
          </p>
          <div className="mt-2 flex gap-2">
            <Button variant="primary" onClick={() => put(asking)}>
              Отметить
            </Button>
            <Button variant="quiet" onClick={() => setAsking(null)}>
              Не отмечать
            </Button>
          </div>
        </div>
      ) : null}

      {mark.error ? (
        <p role="alert" className="mt-1.5 text-[12px] text-danger">
          {(mark.error as ApiError).message}
        </p>
      ) : null}
    </div>
  );
}
