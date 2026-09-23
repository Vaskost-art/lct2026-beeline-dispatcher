import { KIND_TITLES, type EventDraft } from './draft';

interface Props {
  value: EventDraft['kind'];
  onChange: (kind: EventDraft['kind']) => void;
}

/** Выбор вида события: новая заявка, отмена, задержка, бригада выбыла. */
export function KindPicker({ value, onChange }: Props) {
  return (
    <div
      role="group"
      aria-label="Вид события"
      className="flex flex-wrap gap-0.5 rounded-md border border-line bg-raised/60 p-0.5
                 @[520px]:w-fit"
    >
      {KIND_TITLES.map(([kind, title]) => (
        <button
          key={kind}
          type="button"
          aria-pressed={value === kind}
          onClick={() => onChange(kind)}
          className={
            'h-7 rounded-sm px-3 text-[12px] transition-colors duration-[120ms] ' +
            (value === kind
              ? 'bg-panel font-medium text-ink shadow-[0_1px_2px_rgb(10_14_20/0.08)]'
              : 'text-ink-3 hover:text-ink')
          }
        >
          {title}
        </button>
      ))}
    </div>
  );
}
