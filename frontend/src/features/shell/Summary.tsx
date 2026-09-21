import type { ReactNode } from 'react';

import type { PlanPayload } from '../../api/types';

interface Props {
  plan: PlanPayload;
  /** Идёт новый расчёт: числа на экране от прошлого плана. */
  stale: boolean;
  /** Проверки дня: они нужны каждый день и живут на виду, а не в меню. */
  actions: ReactNode;
  /** Когда этот план собран: иначе устаревшие числа не отличить от свежих. */
  builtAt: string;
}

function Figure({
  label,
  value,
  unit,
  stale,
}: {
  label: string;
  value: string;
  unit?: string;
  stale: boolean;
}) {
  return (
    <div
      className={
        'flex min-w-0 flex-col gap-1 transition-opacity duration-[120ms] ' +
        (stale ? 'opacity-45' : '')
      }
    >
      <span className="text-[12px] font-medium text-ink-3">{label}</span>
      <span className="truncate text-[20px] font-semibold leading-none tracking-[-0.015em] tnum">
        {value}
        {unit ? <span className="unit"> {unit}</span> : null}
      </span>
    </div>
  );
}

/** Сводка дня.

Иерархия здесь важнее полноты: первым читается доля закрытых заявок, вторым
то, что требует решения человека, и только потом справочные величины.
*/
export function Summary({ plan, stale, actions, builtAt }: Props) {
  const m = plan.metrics;

  return (
    <section
      data-stale={stale}
      className="flex flex-wrap items-center gap-x-8 gap-y-4 border-b border-line bg-panel px-4 py-3"
    >
      <div data-testid="metric-assigned" data-stale={stale} className="flex min-w-0 flex-col gap-1">
        <span className="text-[12px] font-medium text-ink-3">Заявок в плане</span>
        <span className="flex items-baseline gap-2">
          <span className="text-[34px] font-semibold leading-none tracking-[-0.03em] tnum">
            {m.orders_assigned}
            <span className="text-ink-3">/{m.orders_total}</span>
          </span>
          <span className="text-[13px] font-medium text-ink-3 tnum">
            {Math.round(m.assigned_share * 100)} %
          </span>
        </span>
        <span className="text-[11px] text-ink-3 tnum">план собран в {builtAt}</span>
        <span
          aria-hidden
          className="h-1.5 w-full min-w-[184px] overflow-hidden rounded-full bg-raised"
          title={`${m.orders_assigned} из ${m.orders_total}`}
        >
          <span
            className="block h-full rounded-full bg-ok transition-[width] duration-200"
            style={{ width: `${Math.round(m.assigned_share * 100)}%` }}
          />
        </span>
      </div>

      <span aria-hidden className="hidden h-10 w-px bg-line sm:block" />

      <Figure
        label="Бригад в работе"
        value={`${m.used_engineers} из ${m.engineers_available}`}
        stale={stale}
      />
      <Figure label="Пробег" value={m.total_km.toFixed(1)} unit="км" stale={stale} />
      <Figure
        label="Время в пути"
        value={String(Math.round(m.travel_share * 100))}
        unit="% смены"
        stale={stale}
      />

      <div
        data-testid="day-checks"
        className="hidden flex-wrap items-center gap-2 sm:ml-auto sm:flex"
      >
        {actions}
      </div>

    </section>
  );
}
