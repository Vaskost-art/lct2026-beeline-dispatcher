import { ArrowRight, CheckCircle, Timer, UserMinus, WarningOctagon } from '@phosphor-icons/react';

import type { PlanPayload } from '../../api/types';
import { priorityMark } from '../../priority';
import { plural } from '../../text';

interface Props {
  plan: PlanPayload;
  onUnassigned: () => void;
  onRisk: () => void;
  onShortfall: () => void;
}

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
      className={
        'flex w-full items-center gap-2 rounded-md border px-2 py-1.5 text-left ' +
        'transition-colors duration-[120ms] hover:brightness-[0.98] ' +
        // Очередь решений - единственное место на экране, где написано, что
        // делать. Рамками на белом она была бледнее соседних кнопок отчётов
        // и терялась; тон берётся у самой задачи.
        (tone === 'danger'
          ? 'border-danger/30 bg-danger-soft'
          : 'border-warn/30 bg-warn-soft')
      }
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
      <ArrowRight size={13} weight="bold" aria-hidden className="shrink-0 text-ink-3" />
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
  // Порог опасности один на весь экран: берём оценку сервера, по которой
  // рисует и окно прогноза. Свой порог давал «4 маршрута» против шести
  // «высоких» в окне.
  const tight = plan.risk.routes.filter((route) => route.used && route.risk === 'высокий').length;
  const byId = new Map(plan.orders.map((order) => [order.id, order]));
  const emergencies = plan.unassigned.filter(
    (item) => priorityMark(byId.get(item.order_id)?.priority)?.text === 'авария',
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
          hint={
            emergencies > 0
              ? `из них ${emergencies} ${plural(emergencies, 'авария', 'аварии', 'аварий')}: причины и что делать`
              : 'посмотреть причины и что с ними делать'
          }
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
          hint="высокий риск опоздания: кого предупредить"
          onClick={onRisk}
        />
      ) : null}
      </div>
    </section>
  );
}
