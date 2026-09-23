import { CaretDown, Lightning } from '@phosphor-icons/react';

/** Заголовок полосы события: раскрывает и сворачивает форму. */
export function EventToggle({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      className="flex h-10 w-full items-center gap-2 px-3 text-left"
    >
      <Lightning size={15} weight="fill" aria-hidden className="text-accent" />
      <span className="shrink-0 text-[13px] font-medium">Событие в течение дня</span>
      <span className="truncate text-[12px] text-ink-3">
        новая заявка или авария, отмена, задержка, бригада выбыла
      </span>
      <CaretDown
        size={12}
        weight="bold"
        aria-hidden
        className={'ml-auto text-ink-3 transition-transform ' + (open ? 'rotate-180' : '')}
      />
    </button>
  );
}
