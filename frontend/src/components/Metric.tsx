interface Props {
  id: string;
  title: string;
  value: string;
  hint?: string;
  /** Значение от прошлого расчёта. Пустой квадрат на его месте читается
      как «ноль заявок», поэтому число остаётся, но приглушается. */
  stale?: boolean;
  onClick?: () => void;
}

export function Metric({ id, title, value, hint, stale = false, onClick }: Props) {
  const body = (
    <>
      <span className="text-xs text-muted">{title}</span>
      <span className="text-lg font-semibold">{value}</span>
      {hint ? <span className="text-xs text-muted">{hint}</span> : null}
    </>
  );

  const shell =
    'flex min-w-0 flex-col rounded-lg border border-line bg-panel px-3 py-2 ' +
    (stale ? 'opacity-50' : '');

  if (onClick) {
    return (
      <button
        type="button"
        data-testid={`metric-${id}`}
        data-stale={stale}
        onClick={onClick}
        className={`${shell} text-left hover:border-accent`}
      >
        {body}
      </button>
    );
  }

  return (
    <div data-testid={`metric-${id}`} data-stale={stale} className={shell}>
      {body}
    </div>
  );
}
