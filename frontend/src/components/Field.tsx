import type { ReactNode } from 'react';

interface Props {
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
}

/** Поле формы с подписью и местом для отказа: ошибки показываются по месту,
    а не общим сообщением наверху экрана. */
export function Field({ label, hint, error, children }: Props) {
  return (
    <label className="flex min-w-0 flex-col gap-1">
      <span className="eyebrow">{label}</span>
      {children}
      {hint && !error ? <span className="text-[12px] text-ink-3">{hint}</span> : null}
      {error ? (
        <span role="alert" className="text-[12px] text-danger">
          {error}
        </span>
      ) : null}
    </label>
  );
}
