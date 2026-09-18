import type { PlanPayload } from '../../api/types';
import { Modal } from '../../components/Modal';

interface Props {
  plan: PlanPayload;
  open: boolean;
  onClose: () => void;
}

const TONE: Record<string, string> = {
  высокий: 'text-danger',
  средний: 'text-warn',
  низкий: 'text-ok',
};

/** Прогноз опозданий: где план сломается от первой же задержки. */
export function RiskDialog({ plan, open, onClose }: Props) {
  const routes = plan.risk.routes.filter((route) => route.used);

  return (
    <Modal open={open} title="Прогноз опозданий" onClose={onClose}>
      <p className="mb-3 text-[13px] text-ink-2">{plan.risk.summary}</p>
      <ul className="flex flex-col divide-y divide-line border-y border-line">
        {routes.map((route) => (
          <li key={route.engineer_id} className="flex flex-col gap-0.5 py-2">
            <span className="flex items-baseline gap-3">
              <span className="min-w-0 flex-1 truncate text-[13px] font-medium">
                {route.engineer_id}
              </span>
              <span className={`text-[12px] font-semibold ${TONE[route.risk] ?? 'text-ink-3'}`}>
                {route.risk} риск
              </span>
              <span className="w-24 text-right text-[12px] text-ink-3 tnum">
                запас {route.tolerance_min} <span className="unit">мин</span>
              </span>
            </span>
            <span className="text-[12px] text-ink-2">{route.text}</span>
          </li>
        ))}
      </ul>
    </Modal>
  );
}
