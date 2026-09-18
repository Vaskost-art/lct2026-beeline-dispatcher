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
export function EventPreview({ before, preview }: Props) {
  const counted = preview.diff.changes.reduce<Record<string, number>>((acc, change) => {
    acc[change.status] = (acc[change.status] ?? 0) + 1;
    return acc;
  }, {});

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
