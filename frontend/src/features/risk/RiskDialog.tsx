import type { PlanPayload } from '../../api/types';
import { Modal } from '../../components/Modal';

interface Props {
  plan: PlanPayload;
  open: boolean;
  onClose: () => void;
}

/** Риск это состояние маршрута, а не оттенок текста: бейдж читается с
    первого взгляда и не спорит с соседним числом. */
const BADGE: Record<string, string> = {
  высокий: 'bg-danger-soft text-danger',
  средний: 'bg-raised text-warn',
  низкий: 'bg-ok-soft text-ok',
};

/** Прогноз опозданий: где план сломается от первой же задержки. */
export function RiskDialog({ plan, open, onClose }: Props) {
  const routes = plan.risk.routes.filter((route) => route.used);

  return (
    <Modal open={open} title="Прогноз опозданий" onClose={onClose}>
      <p className="mb-3 max-w-[68ch] text-[13px] text-ink-2">{plan.risk.summary}</p>
      <div className="flex items-center gap-3 border-t border-line pb-1 pt-2">
        <span className="flex-1 text-[11px] font-medium uppercase tracking-[0.05em] text-ink-4">
          Бригада
        </span>
        <span className="w-20 text-[11px] font-medium uppercase tracking-[0.05em] text-ink-4">
          Риск
        </span>
        <span className="w-20 text-right text-[11px] font-medium uppercase tracking-[0.05em] text-ink-4">
          Запас
        </span>
      </div>

      <ul className="flex flex-col divide-y divide-line border-t border-line">
        {routes.map((route) => (
          <li key={route.engineer_id} className="flex flex-col gap-1 py-2.5">
            <span className="flex items-center gap-3">
              <span className="min-w-0 flex-1 truncate text-[13px] font-medium">
                {route.engineer_id}
              </span>
              <span
                className={
                  'w-20 shrink-0 rounded-sm px-1.5 py-0.5 text-center text-[11px] font-semibold uppercase tracking-[0.03em] ' +
                  (BADGE[route.risk] ?? 'bg-raised text-ink-3')
                }
              >
                {route.risk}
              </span>
              <span className="w-20 shrink-0 text-right text-[13px] font-semibold tnum">
                {route.tolerance_min} <span className="unit">мин</span>
              </span>
            </span>
            <span className="max-w-[68ch] text-[12px] text-ink-2">{route.text}</span>
          </li>
        ))}
      </ul>
    </Modal>
  );
}
