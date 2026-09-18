import type { ReactNode } from 'react';

interface Props {
  title?: string;
  children: ReactNode;
  className?: string;
}

export function Card({ title, children, className = '' }: Props) {
  return (
    <section className={`min-w-0 rounded-lg border border-line bg-panel p-3 ${className}`}>
      {title ? <h3 className="mb-2 text-[13px] font-semibold">{title}</h3> : null}
      {children}
    </section>
  );
}
