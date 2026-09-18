import type { ButtonHTMLAttributes, ReactNode } from 'react';

type Variant = 'primary' | 'quiet' | 'shell' | 'danger';

const BASE =
  'inline-flex h-8 items-center gap-2 rounded-md px-3 text-[13px] font-medium ' +
  'whitespace-nowrap transition-colors duration-[120ms] ' +
  // Выключенная кнопка становится нейтральной, а не блёклой цветной:
  // полупрозрачный акцент читается как ошибка отрисовки.
  'disabled:cursor-not-allowed disabled:border-line disabled:bg-raised ' +
  'disabled:text-ink-4 disabled:shadow-none';

const BY_VARIANT: Record<Variant, string> = {
  // Главное действие экрана. На экране оно одно.
  primary: 'bg-accent text-accent-ink hover:brightness-[1.08] active:brightness-95',
  quiet: 'border border-line bg-panel text-ink-2 hover:bg-raised hover:text-ink',
  // Кнопка внутри тёмной оболочки: своя пара цветов, иначе пропадает.
  shell: 'border border-white/12 text-shell-ink hover:bg-white/8',
  danger: 'border border-line bg-panel text-danger hover:bg-danger-soft',
};

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  /** Идёт долгая работа: расчёт занимает до полутора десятков секунд, и без
      обратной связи экран выглядит зависшим. */
  busy?: boolean;
  busyLabel?: string;
  children: ReactNode;
}

export function Button({
  variant = 'quiet',
  busy = false,
  busyLabel = 'Считаем',
  children,
  className = '',
  disabled,
  ...rest
}: Props) {
  return (
    <button
      type="button"
      className={`${BASE} ${BY_VARIANT[variant]} ${className}`}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      {...rest}
    >
      {busy ? (
        <>
          <span
            aria-hidden
            className="size-3 animate-spin rounded-full border-2 border-current border-t-transparent opacity-70"
          />
          {busyLabel}
        </>
      ) : (
        children
      )}
    </button>
  );
}
