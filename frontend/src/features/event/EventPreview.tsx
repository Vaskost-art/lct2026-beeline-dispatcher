import { useState } from 'react';

import type { PlanPayload, ReplanPayload } from '../../api/types';
import { plural } from '../../text';
import { STATUS_TITLES, STATUS_WEIGHT } from './changes';
import { Tile } from './Tile';

interface Props {
  before: PlanPayload;
  preview: ReplanPayload;
  /** Переход к заявке: без него счётчик «сменила место: 5» не отвечает на
      вопрос, кому именно ломается день, и применять событие приходится
      вслепую. */
  onSelect: (orderId: string) => void;
  /** Посчитано минимальной правкой: тогда опоздание к аварии лечится полной. */
  minimal?: boolean;
}

/** Сколько изменений показывать сразу. */
const SHORT_LIST = 4;

/** Что будет, если применить событие.

Рабочий день при этом не меняется: пока не нажато «применить», это только
предпросмотр, и подписан он именно так.
*/
export function EventPreview({ before, preview, onSelect, minimal = false }: Props) {
  const nameOf = (id: string | null) =>
    (id ? preview.engineers.find((engineer) => engineer.id === id)?.name : null) ?? id;

  // Нетронутые заявки перечислять незачем: их десятки, и они как раз то, что
  // НЕ изменилось. Остальное - поимённо.
  const frozen = preview.diff.changes.filter((change) => change.status === 'frozen').length;
  const touched = preview.diff.changes
    .filter((change) => change.status !== 'frozen')
    .slice()
    .sort((a, b) => (STATUS_WEIGHT[a.status] ?? 9) - (STATUS_WEIGHT[b.status] ?? 9));
  // Список открывается коротким: иначе он отодвигает решение «применить или
  // отказаться» за нижний край панели, а именно его и ждут от предпросмотра.
  const [all, setAll] = useState(false);
  const shown = all ? touched : touched.slice(0, SHORT_LIST);

  const arrived = preview.diff.new_order;
  const reaction = preview.diff.reaction;

  return (
    <div data-testid="event-preview" className="flex min-w-0 flex-col gap-2.5">
      <p className="text-[13px] text-ink-2">{preview.diff.event.description}</p>

      {/* Судьба новой заявки - первое, что ищет диспетчер. В списке
          изменений её нет, если она не встала: в плане её и не было. */}
      {arrived ? (
        <p
          data-testid="new-order-outcome"
          className={
            'rounded-md border-l-2 px-2 py-1.5 text-[13px] ' +
            (arrived.engineer_id ? 'border-ok bg-ok-soft' : 'border-danger bg-danger-soft')
          }
        >
          {arrived.engineer_id ? (
            <>
              Заявку {arrived.order_id} берёт «{nameOf(arrived.engineer_id)}».
              {reaction ? (
                <>
                  {' '}Приедет через <span className="font-semibold tnum">{reaction.minutes} мин</span>{' '}
                  после поступления
                  {reaction.within
                    ? ' - в пределах ориентира 1-2 часа.'
                    : ' - дольше ориентира 1-2 часа.'}
                  {!reaction.within && minimal
                    ? ' Минимальная правка сдвигает не больше трёх заявок; полная пересборка '
                      + 'остатка дня двигает больше визитов и чаще успевает в срок.'
                    : null}
                </>
              ) : null}
            </>
          ) : (
            <>Заявка {arrived.order_id} ни к кому не встала. {arrived.reason}</>
          )}
        </p>
      ) : null}

      {preview.diff.lost && preview.diff.lost.length > 0 ? (
        <p role="alert" className="rounded-md border-l-2 border-danger bg-danger-soft px-2 py-1.5 text-[13px]">
          Пересборка сняла {preview.diff.lost.length}{' '}
          {plural(preview.diff.lost.length, 'заявку', 'заявки', 'заявок')}, которые были в плане:{' '}
          {preview.diff.lost.join(', ')}. Точечная правка может их сохранить.
        </p>
      ) : null}

      {/* Три плитки в ряд и на телефоне: столбиком они выталкивали кнопку
          «Применить к дню» за край экрана. */}
      <div className="grid grid-cols-3 gap-2">
        <Tile
          label="Назначено заявок"
          was={before.metrics.orders_assigned}
          now={preview.metrics.orders_assigned}
        />
        <Tile
          label="Пробег"
          was={before.metrics.total_km}
          now={preview.metrics.total_km}
          unit="км"
          digits={1}
          tone="less"
        />
        <Tile
          label="Бригад в работе"
          was={before.metrics.used_engineers}
          now={preview.metrics.used_engineers}
          tone="neutral"
        />
      </div>

      {touched.length > 0 ? (
        <div className="flex flex-col gap-1">
          <span className="eyebrow">Что изменится поимённо</span>
          <ul className="flex flex-col divide-y divide-line rounded-md border border-line">
            {shown.map((change) => (
              <li key={`${change.order_id}-${change.status}`}>
                <button
                  type="button"
                  onClick={() => onSelect(change.order_id)}
                  className="flex w-full flex-wrap items-baseline gap-x-2 gap-y-0.5 px-2 py-1.5
                             text-left transition-colors duration-[120ms] hover:bg-raised"
                >
                  <span className="text-[12px] font-medium tnum">№ {change.order_id}</span>
                  <span
                    className={
                      'text-[12px] ' +
                      (change.status === 'dropped' ? 'text-danger' : 'text-ink-2')
                    }
                  >
                    {STATUS_TITLES[change.status] ?? change.status}
                    {change.status === 'retimed' && change.shift_min ? (
                      <span className="tnum">
                        {' '}
                        {change.shift_min > 0 ? 'позже' : 'раньше'} на {Math.abs(change.shift_min)} мин
                        {/* Визит раньше при задержке бригады выглядит ошибкой,
                            если не сказать, откуда взялось время. */}
                        {change.shift_min < 0 ? ': впереди освободилось время' : ''}
                      </span>
                    ) : null}
                    {change.status === 'dropped' ? ': в карточке причина и что можно сделать' : null}
                  </span>
                  {change.from_engineer && change.to_engineer &&
                  change.from_engineer !== change.to_engineer ? (
                    <span className="text-[11px] text-ink-3">
                      {nameOf(change.from_engineer)} → {nameOf(change.to_engineer)}
                    </span>
                  ) : null}
                </button>
              </li>
            ))}
          </ul>
          {touched.length > SHORT_LIST ? (
            <button
              type="button"
              onClick={() => setAll(!all)}
              className="-mx-1 w-fit rounded px-1 py-1 text-[12px] font-medium text-ink
                         underline underline-offset-2 hover:bg-raised"
            >
              {all ? 'Свернуть список' : `Показать все ${touched.length}`}
            </button>
          ) : null}
        </div>
      ) : null}

      {frozen > 0 ? (
        <p className="text-[12px] text-ink-3">
          Ещё <span className="tnum">{frozen}</span>{' '}
          {plural(frozen, 'заявка', 'заявки', 'заявок')} на участке уже{' '}
          {plural(frozen, 'начата', 'начаты', 'начаты')}, событие их не трогает.
        </p>
      ) : null}
    </div>
  );
}
