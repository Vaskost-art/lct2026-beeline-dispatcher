import { useState } from 'react';

import type { PlanPayload, ReplanPayload } from '../../api/types';
import { plural } from '../../text';

interface Props {
  before: PlanPayload;
  preview: ReplanPayload;
  /** Переход к заявке: без него счётчик «сменила место: 5» не отвечает на
      вопрос, кому именно ломается день, и применять событие приходится
      вслепую. */
  onSelect: (orderId: string) => void;
}

/** Сколько изменений показывать сразу. */
const SHORT_LIST = 4;

const STATUS_TITLES: Record<string, string> = {
  moved: 'передана другой бригаде',
  resequenced: 'сменила место в маршруте',
  dropped: 'выпала из плана',
  added: 'добавлена в план',
  frozen: 'уже начата, не трогаем',
};

interface TileProps {
  label: string;
  was: number;
  now: number;
  unit?: string;
  /** Для пробега меньше значит лучше, для заявок наоборот. Без этого
      признака сокращение километров красится как ухудшение. */
  lessIsBetter?: boolean;
}

function Tile({ label, was, now, unit, lessIsBetter = false }: TileProps) {
  const diff = now - was;
  const better = lessIsBetter ? diff < 0 : diff > 0;
  const tone = better ? 'text-ok' : 'text-danger';

  return (
    <div className="flex min-w-0 flex-col gap-1 rounded-md border border-line bg-panel px-3 py-2">
      <span className="text-[11px] font-medium text-ink-3">{label}</span>
      <span className="flex items-baseline gap-1.5">
        <span className="text-[22px] font-semibold leading-none tracking-[-0.02em] tnum">{now}</span>
        {unit ? <span className="unit">{unit}</span> : null}
        {diff === 0 ? null : (
          <span className={`text-[13px] font-semibold tnum ${tone}`}>
            {diff > 0 ? '+' : '−'}
            {Math.abs(diff)}
          </span>
        )}
      </span>
      <span className="text-[11px] text-ink-4 tnum">
        {diff === 0 ? 'без изменений' : `было ${was}`}
      </span>
    </div>
  );
}

/** Что будет, если применить событие.

Рабочий день при этом не меняется: пока не нажато «применить», это только
предсказание, и подписано оно именно так.
*/
export function EventPreview({ before, preview, onSelect }: Props) {
  const nameOf = (id: string | null) =>
    (id ? preview.engineers.find((engineer) => engineer.id === id)?.name : null) ?? id;

  // Нетронутые заявки перечислять незачем: их десятки, и они как раз то, что
  // НЕ изменилось. Остальное - поимённо.
  const frozen = preview.diff.changes.filter((change) => change.status === 'frozen').length;
  const touched = preview.diff.changes.filter((change) => change.status !== 'frozen');
  // Список открывается коротким: иначе он отодвигает решение «применить или
  // отказаться» за нижний край панели, а именно его и ждут от предпросмотра.
  const [all, setAll] = useState(false);
  const shown = all ? touched : touched.slice(0, SHORT_LIST);

  return (
    <div data-testid="event-preview" className="flex min-w-0 flex-col gap-2.5">
      <p className="text-[13px] text-ink-2">{preview.diff.event.description}</p>

      <div className="grid gap-2 sm:grid-cols-3">
        <Tile
          label="Назначено заявок"
          was={before.metrics.orders_assigned}
          now={preview.metrics.orders_assigned}
        />
        <Tile
          label="Пробег"
          was={Math.round(before.metrics.total_km)}
          now={Math.round(preview.metrics.total_km)}
          unit="км"
          lessIsBetter
        />
        <Tile
          label="Бригад в работе"
          was={before.metrics.used_engineers}
          now={preview.metrics.used_engineers}
          lessIsBetter
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
              className="w-fit text-[12px] font-medium text-accent hover:underline"
            >
              {all ? 'Свернуть список' : `Показать все ${touched.length}`}
            </button>
          ) : null}
        </div>
      ) : null}

      {frozen > 0 ? (
        <p className="text-[12px] text-ink-3">
          Ещё <span className="tnum">{frozen}</span>{' '}
          {plural(frozen, 'заявку', 'заявки', 'заявок')} бригады уже начали - событие их
          не трогает.
        </p>
      ) : null}
    </div>
  );
}
