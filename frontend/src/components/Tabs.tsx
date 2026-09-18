interface Item {
  key: string;
  title: string;
  count?: number;
  tone?: 'plain' | 'alert';
}

interface Props {
  items: Item[];
  value: string;
  onChange: (key: string) => void;
}

/** Вкладки списка. Счётчик рядом с названием: он часть смысла вкладки,
    а не украшение. */
export function Tabs({ items, value, onChange }: Props) {
  return (
    <div role="tablist" className="flex h-9 shrink-0 items-stretch gap-4 border-b border-line px-3">
      {items.map((item) => {
        const active = item.key === value;
        const alert = item.tone === 'alert' && (item.count ?? 0) > 0;
        return (
          <button
            key={item.key}
            role="tab"
            type="button"
            aria-selected={active}
            onClick={() => onChange(item.key)}
            className={
              'relative flex min-w-0 items-center gap-1.5 text-[13px] transition-colors duration-[120ms] ' +
              (active ? 'font-semibold text-ink' : 'text-ink-3 hover:text-ink')
            }
          >
            <span className="truncate">{item.title}</span>
            {item.count === undefined ? null : (
              <span
                className={
                  'rounded-sm px-1 text-[11px] font-semibold tnum ' +
                  (alert ? 'bg-danger-soft text-danger' : 'bg-raised text-ink-3')
                }
              >
                {item.count}
              </span>
            )}
            {active ? (
              <span aria-hidden className="absolute inset-x-0 -bottom-px h-0.5 rounded-t-sm bg-accent" />
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
