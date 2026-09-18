import { Metric } from '../../components/Metric';
import type { PlanPayload } from '../../api/types';

interface Props {
  plan: PlanPayload;
  /** Идёт новый расчёт: числа на экране от прошлого плана. */
  stale: boolean;
  onShortfall: () => void;
}

/** Пять величин, по которым диспетчер судит о дне. */
export function Metrics({ plan, stale, onShortfall }: Props) {
  const m = plan.metrics;
  const missing = plan.shortfall.missing;

  return (
    <div className="grid grid-cols-2 gap-2 px-4 py-2 sm:grid-cols-3 lg:grid-cols-5">
      <Metric
        id="assigned"
        title="Назначено"
        value={`${m.orders_assigned} из ${m.orders_total}`}
        hint={`${Math.round(m.assigned_share * 100)}%`}
        stale={stale}
      />
      <Metric
        id="crews"
        title="Людей в смене"
        value={`${m.used_engineers} из ${m.engineers_available}`}
        hint="получили хотя бы одну заявку"
        stale={stale}
      />
      <Metric
        id="km"
        title="Пробег"
        value={`${m.total_km.toFixed(1)} км`}
        hint={`${m.avg_km_per_order.toFixed(1)} км на заявку`}
        stale={stale}
      />
      <Metric
        id="travel"
        title="В пути"
        value={`${Math.round(m.travel_share * 100)} %`}
        hint={`${m.total_travel_min} мин в дороге`}
        stale={stale}
      />
      <Metric
        id="shortfall"
        title="Нужно ещё бригад"
        value={missing > 0 ? String(missing) : 'нисколько'}
        hint={missing > 0 ? 'разбор причин' : 'все заявки разошлись'}
        stale={stale}
        onClick={onShortfall}
      />
    </div>
  );
}
