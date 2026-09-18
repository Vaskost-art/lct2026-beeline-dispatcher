import { ArrowRight, CheckCircle, Timer, UserMinus, WarningOctagon } from '@phosphor-icons/react';

import type { PlanPayload } from '../../api/types';
import { plural } from '../../text';

interface Props {
  plan: PlanPayload;
  onUnassigned: () => void;
  onRisk: () => void;
  onShortfall: () => void;
}

/** Сколько минут запаса считается опасным: ниже этого маршрут рвётся от
    первой же задержки на месте. */
const TIGHT_MIN = 10;

interface RowProps {
  icon: typeof Timer;
  tone: 'danger' | 'warn';
  title: string;
  hint: string;
  onClick: () => void;
}

function Row({ icon: Icon, tone, title, hint, onClick }: RowProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center gap-2 rounded-md border border-line px-2 py-1.5
                 text-left transition-colors duration-[120ms] hover:border-line-2 hover:bg-raised"
    >
      <Icon
        size={16}
        weight="fill"
        aria-hidden
        className={'shrink-0 ' + (tone === 'danger' ? 'text-danger' : 'text-warn')}
      />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13px] font-medium">{title}</span>
        <span className="block truncate text-[11px] text-ink-3">{hint}</span>
      </span>
      <ArrowRight size={13} weight="bold" aria-hidden className="shrink-0 text-ink-4" />
    </button>
  );
}

/** Очередь решений диспетчера.

День это не набор чисел, а список того, что требует человека: заявки без
исполнителя, маршруты, которые порвутся от первой задержки, нехватка людей.
Каждая строка ведёт туда, где это чинится.
*/
export function Decisions({ plan, onUnassigned, onRisk, onShortfall }: Props) {
  const left = plan.metrics.orders_unassigned;
  const missing = plan.shortfall.missing;
  const tight = plan.risk.routes.filter(
    (route) => route.used && route.tolerance_min < TIGHT_MIN,
  ).length;

  const nothing = left === 0 && tight === 0 && missing === 0;

  return (
    <section className="flex min-w-0 shrink-0 flex-col gap-1 rounded-lg border border-line bg-panel px-2 py-1.5">
      <span className="px-1 text-[11px] font-semibold uppercase tracking-[0.05em] text-ink-3">
        Требуют решения
      </span>
      <div className="grid gap-1 sm:grid-cols-2 lg:grid-cols-3">

      {nothing ? (
        <p className="flex items-center gap-2 px-2 py-1.5 text-[13px] text-ink-2">
          <CheckCircle size={16} weight="fill" aria-hidden className="text-ok" />
          День собран: все заявки разошлись, запас по времени есть у всех бригад.
        </p>
      ) : null}

      {left > 0 ? (
        <Row
          icon={WarningOctagon}
          tone="danger"
          title={`${left} ${plural(left, 'заявка', 'заявки', 'заявок')} без исполнителя`}
          hint="посмотреть причины и что с ними делать"
          onClick={onUnassigned}
        />
      ) : null}

      {missing > 0 ? (
        <Row
          icon={UserMinus}
          tone="warn"
          title={`Нужно ещё ${missing} ${plural(missing, 'бригада', 'бригады', 'бригад')}`}
          hint="сколько людей закроют день полностью"
          onClick={onShortfall}
        />
      ) : null}

      {tight > 0 ? (
        <Row
          icon={Timer}
          tone="warn"
          title={`${tight} ${plural(tight, 'маршрут', 'маршрута', 'маршрутов')} без запаса времени`}
          hint={`порвутся от задержки больше ${TIGHT_MIN} минут`}
          onClick={onRisk}
        />
      ) : null}
      </div>
    </section>
  );
}
