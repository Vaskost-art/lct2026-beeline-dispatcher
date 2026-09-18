import { ArrowRight, Warning } from '@phosphor-icons/react';

import type { PlanPayload } from '../../api/types';
import { plural } from '../../text';

interface Props {
  plan: PlanPayload;
  /** Идёт новый расчёт: числа на экране от прошлого плана. */
  stale: boolean;
  onShortfall: () => void;
}

function Figure({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <span className="eyebrow">{label}</span>
      <span className="truncate text-[15px] font-semibold tnum">
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
export function Summary({ plan, stale, onShortfall }: Props) {
  const m = plan.metrics;
  const missing = plan.shortfall.missing;
  const left = m.orders_unassigned;

  return (
    <section
      data-stale={stale}
      className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-line bg-panel px-4 py-3
                 transition-opacity duration-[120ms] data-[stale=true]:opacity-55"
    >
      <div data-testid="metric-assigned" data-stale={stale} className="flex min-w-0 flex-col gap-1">
        <span className="eyebrow">Заявки разошлись</span>
        <span className="flex items-baseline gap-2">
          <span className="readout">
            {m.orders_assigned}
            <span className="text-ink-4">/{m.orders_total}</span>
          </span>
          <span className="text-[12px] font-medium text-ink-3 tnum">
            {Math.round(m.assigned_share * 100)} %
          </span>
        </span>
        <span
          aria-hidden
          className="h-1 w-40 overflow-hidden rounded-sm bg-raised"
          title={`${m.orders_assigned} из ${m.orders_total}`}
        >
          <span
            className="block h-full rounded-sm bg-ok"
            style={{ width: `${Math.round(m.assigned_share * 100)}%` }}
          />
        </span>
      </div>

      <span aria-hidden className="hidden h-10 w-px bg-line sm:block" />

      <Figure
        label="Бригад в работе"
        value={`${m.used_engineers} из ${m.engineers_available}`}
      />
      <Figure label="Пробег" value={m.total_km.toFixed(1)} unit="км" />
      <Figure label="В пути" value={String(Math.round(m.travel_share * 100))} unit="%" />
      <Figure label="Расчёт" value={m.solve_seconds.toFixed(1)} unit="с" />

      <button
        type="button"
        data-testid="metric-shortfall"
        data-stale={stale}
        onClick={onShortfall}
        className={
          'flex w-full items-center gap-3 rounded-lg border px-3 py-2 text-left sm:ml-auto sm:w-auto ' +
          'transition-colors duration-[120ms] ' +
          (missing > 0
            ? 'border-accent/35 bg-accent-soft hover:border-accent'
            : 'border-line bg-panel hover:bg-raised')
        }
      >
        {missing > 0 ? (
          <Warning size={18} weight="fill" aria-hidden className="shrink-0 text-accent" />
        ) : null}
        <span className="flex min-w-0 flex-col">
          <span className="eyebrow">{missing > 0 ? 'Не хватает людей' : 'Людей хватает'}</span>
          <span className="truncate text-[13px] font-semibold">
            {missing > 0
              ? `Нужно ещё ${missing} ${plural(missing, 'бригада', 'бригады', 'бригад')}`
              : `Все ${m.orders_total} заявок разошлись`}
          </span>
          {left > 0 ? (
            <span className="truncate text-[11px] text-ink-3">
              {left} {plural(left, 'заявка', 'заявки', 'заявок')} без исполнителя
            </span>
          ) : null}
        </span>
        <ArrowRight size={14} weight="bold" aria-hidden className="shrink-0 text-ink-4" />
      </button>
    </section>
  );
}
