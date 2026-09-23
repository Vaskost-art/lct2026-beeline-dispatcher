import { decimal } from '../../text';

interface TileProps {
  label: string;
  was: number;
  now: number;
  unit?: string;
  /** Знаков после запятой: пробег показывается так же, как в сводке. */
  digits?: number;
  /** Как красить разницу. Для пробега меньше значит лучше, для заявок
      больше; число бригад само по себе ни хорошо, ни плохо: уход бригады
      не должен выглядеть улучшением. */
  tone?: 'more' | 'less' | 'neutral';
}

/** Показатель дня до и после события. */
export function Tile({ label, was, now, unit, digits = 0, tone = 'more' }: TileProps) {
  const diff = Number((now - was).toFixed(digits));
  const better = tone === 'less' ? diff < 0 : diff > 0;
  const color = tone === 'neutral' ? 'text-ink-2' : better ? 'text-ok' : 'text-danger';
  const show = (value: number) => decimal(value, digits);

  return (
    <div className="flex min-w-0 flex-col gap-1 rounded-md border border-line bg-panel px-3 py-2">
      <span className="text-[11px] font-medium text-ink-3">{label}</span>
      {/* Разница переносится под число: на телефоне три плитки в ряд узкие. */}
      <span className="flex flex-wrap items-baseline gap-x-1.5">
        <span className="text-[22px] font-semibold leading-none tracking-[-0.02em] tnum">
          {show(now)}
        </span>
        {unit ? <span className="unit">{unit}</span> : null}
        {diff === 0 ? null : (
          <span className={`text-[13px] font-semibold tnum ${color}`}>
            {diff > 0 ? '+' : '−'}
            {show(Math.abs(diff))}
          </span>
        )}
      </span>
      <span className="text-[11px] text-ink-3 tnum">
        {diff === 0 ? 'без изменений' : `было ${show(was)}`}
      </span>
    </div>
  );
}
