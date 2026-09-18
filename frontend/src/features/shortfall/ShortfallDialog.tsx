import type { PlanPayload } from '../../api/types';
import { Modal } from '../../components/Modal';
import { plural } from '../../text';

interface Props {
  plan: PlanPayload;
  open: boolean;
  onClose: () => void;
}

/** Разбор нехватки людей.

Различает два случая: заявку заберёт дополнительная бригада, и заявку не
берёт никто. Во втором случае искать людей бесполезно, и это сказано прямо.
*/
export function ShortfallDialog({ plan, open, onClose }: Props) {
  const s = plan.shortfall;
  const stuck = s.still_unassigned;

  return (
    <Modal open={open} title="Сколько ещё нужно бригад" onClose={onClose}>
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap gap-x-8 gap-y-3 rounded-md border border-line bg-raised px-3 py-3">
          <span className="flex min-w-0 flex-col">
            <span className="eyebrow">Нужно ещё</span>
            <span className="readout">
              {s.missing} <span className="unit">{plural(s.missing, 'бригада', 'бригады', 'бригад')}</span>
            </span>
          </span>
          <span className="flex min-w-0 flex-col">
            <span className="eyebrow">Заберут заявок</span>
            <span className="readout">{s.assigned}</span>
          </span>
          <span className="flex min-w-0 flex-col">
            <span className="eyebrow">Не возьмёт никто</span>
            <span className="readout">{stuck}</span>
          </span>
        </div>

        {s.missing > 0 ? (
          <p className="text-[13px] text-ink-2">
            Сервис добавлял бригады по одной, пока каждая новая забирала хотя бы одну заявку.
            Столько людей хватит, чтобы закрыть день полностью.
          </p>
        ) : (
          <p className="text-[13px] text-ink-2">
            Людей хватает: все заявки, которые вообще можно выполнить, уже разошлись.
          </p>
        )}

        {stuck > 0 ? (
          <p className="rounded-md border border-accent/30 bg-accent-soft px-3 py-2 text-[13px] text-ink">
            {s.reason || 'Эти заявки не берёт даже свободная бригада: мешает окно или требования заявки.'}
          </p>
        ) : null}
      </div>
    </Modal>
  );
}
