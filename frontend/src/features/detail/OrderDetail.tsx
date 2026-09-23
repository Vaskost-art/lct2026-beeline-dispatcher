import { X } from '@phosphor-icons/react';
import { Fragment, useEffect, useRef } from 'react';

import { useExplanation } from '../../api/queries';
import type { Order } from '../../api/types';
import { Alternatives } from './Alternatives';
import { ReassignBox } from './ReassignBox';
import { StatusMarks } from './StatusMarks';

interface Props {
  region: string;
  orderId: string;
  order: Order | undefined;
  /** Что отмечено по этой заявке сейчас. */
  status: string;
  /** Кому можно передать заявку: бригады этого участка. */
  crews: { id: string; name: string }[];
  onClose: () => void;
}

/** Объяснение назначения заявки.

Выезжает поверх карты и закрывается по Escape: диспетчер разбирается с одной
заявкой, не теряя из виду весь план.
*/
export function OrderDetail({ region, orderId, order, status, crews, onClose }: Props) {
  const explain = useExplanation(region, orderId);
  const panel = useRef<HTMLElement>(null);
  const closed = status === 'Завершено' || status === 'Отменена';
  const started = status === 'В пути' || status === 'Выполняется';
  const data = explain.data;

  // Фокус переходит в карточку: иначе с клавиатуры до неё не добраться.
  useEffect(() => panel.current?.focus(), []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      // Поверх карточки может быть открыто окно: Escape закрывает его, а не
      // обе панели сразу.
      if (event.key !== 'Escape') return;
      if (document.querySelector('[role="dialog"][data-state="open"]')) return;
      onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  // На узком экране карточка держится за окно, а не за свой контейнер: тот
  // уезжает за нижний край при прокрутке страницы, и вместе с ним уходило
  // действие «Передать другой бригаде».
  return (
    <aside
      ref={panel}
      tabIndex={-1}
      data-testid="detail"
      aria-label={`Заявка ${orderId}`}
      className="fixed inset-x-0 bottom-0 z-40 flex max-h-[82dvh] flex-col overflow-hidden outline-none
                 rounded-t-lg border border-line bg-panel
                 shadow-[0_12px_40px_rgb(10_14_20/0.18)]
                 lg:absolute lg:inset-y-2 lg:bottom-auto lg:left-auto lg:right-2
                 lg:max-h-none lg:w-[380px] lg:rounded-lg"
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

      <div className="scroll-fade min-h-0 flex-1 overflow-auto px-3 py-3">
        <StatusMarks
          region={region}
          orderId={orderId}
          status={status}
          assigned={data ? data.assigned : true}
        />

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

            {data.assigned && order && order.equipment.length > 0 ? (
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

            <Alternatives
              items={data.alternatives}
              total={data.alternatives_total}
              collapsed={data.assigned}
            />

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
          <div>
          {closed || started ? (
            <p className="text-[12px] text-ink-3">
              Заявка в состоянии «{status}»: переносить её другой бригаде поздно.
            </p>
          ) : (
            <ReassignBox
              region={region}
              orderId={orderId}
              holder={data.assigned ? data.engineer_id : undefined}
              crews={crews}
              alternatives={data.alternatives}
            />
          )}
          </div>
        </div>
      ) : null}
    </aside>
  );
}
