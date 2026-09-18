import type { ButtonHTMLAttributes, ReactNode } from 'react';

type Variant = 'primary' | 'ghost' | 'danger';

const BASE =
  'inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium ' +
  'transition-colors disabled:cursor-not-allowed disabled:opacity-60 ' +
  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';

const BY_VARIANT: Record<Variant, string> = {
  primary: 'bg-accent text-accent-text hover:brightness-110',
  ghost: 'border border-line bg-panel text-text hover:border-accent',
  danger: 'border border-line bg-panel text-danger hover:border-danger',
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
  variant = 'ghost',
  busy = false,
  busyLabel = 'Считаем…',
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
      {busy ? busyLabel : children}
    </button>
  );
}
