import type { PlanPayload } from '../../api/types';
import { Modal } from '../../components/Modal';

interface Props {
  plan: PlanPayload;
  open: boolean;
  onClose: () => void;
}

/** Ведомость на выдачу: что каждая бригада забирает в офисе утром.

Оборудование следует из плана, а не ограничивает его: это лист выдачи, а не
склад с остатками.
*/
export function PickupDialog({ plan, open, onClose }: Props) {
  const total = plan.pickup.reduce((sum, row) => sum + row.total, 0);

  return (
    <Modal open={open} title="Что взять в офисе" onClose={onClose}>
      {plan.pickup.length === 0 ? (
        <p className="text-[13px] text-ink-3">
          По этому плану везти нечего: все работы без установки оборудования.
        </p>
      ) : (
        <>
          <p className="mb-3 text-[13px] text-ink-2">
            Всего к выдаче <span className="font-semibold tnum">{total}</span> устройств
            на <span className="tnum">{plan.pickup.length}</span> бригад.
          </p>
          <ul className="flex flex-col divide-y divide-line border-y border-line">
            {plan.pickup.map((row) => (
              <li key={row.engineer_id} className="flex items-baseline gap-3 py-2">
                <span className="min-w-0 flex-1 truncate text-[13px] font-medium">
                  {row.engineer_id}
                </span>
                <span className="text-[13px] text-ink-2">{row.text}</span>
                <span className="w-10 text-right text-[13px] font-semibold tnum">{row.total}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </Modal>
  );
}
