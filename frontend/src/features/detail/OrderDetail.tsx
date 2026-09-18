import { X } from '@phosphor-icons/react';
import { Fragment, useEffect, useState } from 'react';

import { useExplanation, useReassign } from '../../api/queries';
import type { ApiError } from '../../api/client';
import type { Order } from '../../api/types';
import { Button } from '../../components/Button';
import { Alternatives } from './Alternatives';

interface Props {
  region: string;
  orderId: string;
  order: Order | undefined;
  /** Кому можно передать заявку: бригады этого участка. */
  crews: { id: string; name: string }[];
  onClose: () => void;
}

/** Объяснение назначения заявки.

Выезжает поверх карты и закрывается по Escape: диспетчер разбирается с одной
заявкой, не теряя из виду весь план.
*/
export function OrderDetail({ region, orderId, order, crews, onClose }: Props) {
  const explain = useExplanation(region, orderId);
  const reassign = useReassign();
  // Выбор бригады и подтверждение разделены: список без кнопки не говорит,
  // применится ли решение и когда.
  const [picked, setPicked] = useState('');
  const data = explain.data;

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <aside
      data-testid="detail"
      aria-label={`Заявка ${orderId}`}
      className="absolute inset-x-0 bottom-0 z-20 flex max-h-[72%] flex-col overflow-hidden
                 rounded-lg border border-line bg-panel
                 shadow-[0_12px_40px_rgb(10_14_20/0.18)]
                 lg:inset-y-2 lg:left-auto lg:right-2 lg:max-h-none lg:w-[380px]"
    >
      <header className="sticky top-0 z-10 flex items-start gap-2 border-b border-line bg-panel px-3 py-2">
        <div className="min-w-0 flex-1">
          <p className="text-[12px] font-medium text-ink-3">Заявка</p>
          <p data-testid="detail-order" className="text-[15px] font-semibold tnum">
            № {orderId}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Закрыть карточку"
          className="rounded-md p-1 text-ink-3 hover:bg-raised hover:text-ink"
        >
          <X size={16} />
        </button>
      </header>

      <div className="min-h-0 flex-1 overflow-auto px-3 py-3">
        {explain.isPending ? <p className="text-[13px] text-ink-3">Собираем объяснение…</p> : null}

        {explain.error ? (
          <p role="alert" className="text-[13px] text-danger">
            Не удалось объяснить назначение. Попробуйте выбрать заявку ещё раз.
          </p>
        ) : null}

        {data ? (
          <>
            <p
              className={
                'rounded-md border-l-2 bg-raised/60 px-2 py-1.5 text-[13px] font-medium ' +
                (data.assigned ? 'border-ok' : 'border-danger')
              }
            >
              {data.headline}
            </p>

            {data.reason ? <p className="mt-2 text-[13px] text-ink-2">{data.reason}</p> : null}
            {data.route_reason ? (
              <p className="mt-2 text-[13px] text-ink-2">{data.route_reason}</p>
            ) : null}
            {data.timing_reason ? (
              <p className="mt-1 text-[13px] text-ink-2">{data.timing_reason}</p>
            ) : null}

            {order && order.equipment.length > 0 ? (
              <p className="mt-3 flex flex-wrap items-center gap-1 text-[12px] text-ink-3">
                Везём:
                {order.equipment.map((item) => (
                  <span
                    key={item}
                    className="rounded-sm border border-line bg-raised px-1 text-[11px] text-ink-2"
                  >
                    {item}
                  </span>
                ))}
              </p>
            ) : null}

            <Alternatives items={data.alternatives} total={data.alternatives_total} />

            <details className="mt-4 border-t border-line pt-3">
              <summary className="cursor-pointer text-[13px] font-semibold">
                Подробности заявки
              </summary>
              <dl className="mt-2 grid grid-cols-[minmax(0,124px)_minmax(0,1fr)] gap-x-3 gap-y-2">
                {data.facts.map(([name, value]) => (
                  // Fragment, а не div с display:contents: у такого элемента
                  // нет собственного прямоугольника, и проверка вёрстки
                  // сравнивает детей с пустым контейнером.
                  <Fragment key={name}>
                    <dt className="text-[12px] text-ink-3">{name}</dt>
                    <dd className="min-w-0 text-[12px] text-ink">{value}</dd>
                  </Fragment>
                ))}
              </dl>
            </details>

          </>
        ) : null}
      </div>

      {data ? (
        <div className="shrink-0 border-t border-line bg-panel px-3 py-2.5">
          {reassign.isSuccess ? (
            <p className="rounded-md bg-ok-soft px-2 py-1.5 text-[12px] text-ink">
              Заявка передана бригаде «{picked}». Она закреплена и останется у неё при
              следующем пересчёте.
            </p>
          ) : (
            <>
              <span className="text-[12px] font-medium text-ink-3">Передать другой бригаде</span>
              <div className="mt-1 flex gap-2">
                <select
                  aria-label="Передать бригаде"
                  value={picked}
                  onChange={(event) => setPicked(event.target.value)}
                  className="h-8 min-w-0 flex-1 rounded-md border border-line bg-panel px-2 text-[13px]"
                >
                  <option value="">Выберите бригаду</option>
                  {crews
                    .filter((crew) => crew.id !== data.engineer_id)
                    .map((crew) => (
                      <option key={crew.id} value={crew.id}>
                        {crew.name}
                      </option>
                    ))}
                </select>
                <Button
                  variant="primary"
                  disabled={!picked}
                  busy={reassign.isPending}
                  busyLabel="Переносим"
                  onClick={() =>
                    reassign.mutate({ region, order_id: orderId, engineer_id: picked })
                  }
                >
                  Передать
                </Button>
              </div>
              {reassign.error ? (
                <p role="alert" className="mt-1.5 text-[12px] text-danger">
                  {(reassign.error as ApiError).message}
                </p>
              ) : null}
            </>
          )}
        </div>
      ) : null}
    </aside>
  );
}
