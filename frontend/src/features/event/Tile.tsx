interface TileProps {
  label: string;
  was: number;
  now: number;
  unit?: string;
  /** Для пробега меньше значит лучше, для заявок наоборот. Без этого
      признака сокращение километров красится как ухудшение. */
  lessIsBetter?: boolean;
}

/** Показатель дня до и после события. */
export function Tile({ label, was, now, unit, lessIsBetter = false }: TileProps) {
  const diff = now - was;
  const better = lessIsBetter ? diff < 0 : diff > 0;
  const tone = better ? 'text-ok' : 'text-danger';

  return (
    <div className="flex min-w-0 flex-col gap-1 rounded-md border border-line bg-panel px-3 py-2">
      <span className="text-[11px] font-medium text-ink-3">{label}</span>
      {/* Разница переносится под число: на телефоне три плитки в ряд узкие. */}
      <span className="flex flex-wrap items-baseline gap-x-1.5">
        <span className="text-[22px] font-semibold leading-none tracking-[-0.02em] tnum">{now}</span>
        {unit ? <span className="unit">{unit}</span> : null}
        {diff === 0 ? null : (
          <span className={`text-[13px] font-semibold tnum ${tone}`}>
            {diff > 0 ? '+' : '−'}
            {Math.abs(diff)}
          </span>
        )}
      </span>
      <span className="text-[11px] text-ink-3 tnum">
        {diff === 0 ? 'без изменений' : `было ${was}`}
      </span>
    </div>
  );
}
