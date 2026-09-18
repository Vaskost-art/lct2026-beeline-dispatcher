import type { PlanPayload, ReplanPayload } from '../../api/types';

interface Props {
  before: PlanPayload;
  preview: ReplanPayload;
}

const STATUS_TITLES: Record<string, string> = {
  moved: 'передана другой бригаде',
  resequenced: 'сменила место в маршруте',
  dropped: 'выпала из плана',
  added: 'добавлена в план',
  frozen: 'уже начата, не трогаем',
};

interface DeltaProps {
  was: number;
  now: number;
  unit?: string;
  /** Для пробега меньше значит лучше, для заявок наоборот. Без этого
      признака сокращение километров красится как ухудшение. */
  lessIsBetter?: boolean;
}

function Delta({ was, now, unit, lessIsBetter = false }: DeltaProps) {
  const diff = now - was;
  const better = lessIsBetter ? diff < 0 : diff > 0;
  const tone = diff === 0 ? 'text-ink-3' : better ? 'text-ok' : 'text-danger';
  return (
    <span className="tnum">
      <span className="text-ink-3">{was}</span>
      <span className="text-ink-4"> → </span>
      <span className="font-semibold">{now}</span>
      {unit ? <span className="unit"> {unit}</span> : null}
      {diff === 0 ? null : (
        <span className={`ml-1 ${tone}`}>
          ({diff > 0 ? '+' : ''}
          {diff})
        </span>
      )}
    </span>
  );
}

/** Что будет, если применить событие.

Рабочий день при этом не меняется: пока не нажато «применить», это только
предсказание, и подписано оно именно так.
*/
export function EventPreview({ before, preview }: Props) {
  const counted = preview.diff.changes.reduce<Record<string, number>>((acc, change) => {
    acc[change.status] = (acc[change.status] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div data-testid="event-preview" className="flex min-w-0 flex-col gap-2">
      <p className="text-[13px] text-ink-2">{preview.diff.event.description}</p>

      <div className="flex flex-wrap gap-x-6 gap-y-1 rounded-md border border-line bg-raised px-3 py-2 text-[13px]">
        <span className="flex items-baseline gap-2">
          <span className="eyebrow">Назначено</span>
          <Delta
            was={before.metrics.orders_assigned}
            now={preview.metrics.orders_assigned}
          />
        </span>
        <span className="flex items-baseline gap-2">
          <span className="eyebrow">Пробег</span>
          <Delta
            was={Math.round(before.metrics.total_km)}
            now={Math.round(preview.metrics.total_km)}
            unit="км"
            lessIsBetter
          />
        </span>
        <span className="flex items-baseline gap-2">
          <span className="eyebrow">Бригад</span>
          <Delta
            was={before.metrics.used_engineers}
            now={preview.metrics.used_engineers}
            lessIsBetter
          />
        </span>
      </div>

      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-ink-2">
        {Object.entries(counted).map(([status, count]) => (
          <li key={status}>
            {STATUS_TITLES[status] ?? status}: <span className="tnum font-semibold">{count}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
