import type { PlanPayload } from '../../api/types';
import { Button } from '../../components/Button';
import { Modal } from '../../components/Modal';
import { plural } from '../../text';

interface Props {
  plan: PlanPayload;
  open: boolean;
  onClose: () => void;
  /** Из разбора видно, что делать дальше: посмотреть сами заявки или
      выгрузить обоснование для разговора о людях. */
  onShowUnassigned: () => void;
  onExport: () => void;
}

/** Разбор нехватки людей.

Различает два случая: заявку заберёт дополнительная бригада, и заявку не
берёт никто. Во втором случае искать людей бесполезно, и это сказано прямо.
*/
export function ShortfallDialog({ plan, open, onClose, onShowUnassigned, onExport }: Props) {
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
            <span className="eyebrow">Станет назначено</span>
            <span className="readout">
              {s.assigned}
              <span className="text-ink-4">/{plan.metrics.orders_total}</span>
            </span>
          </span>
          <span className="flex min-w-0 flex-col">
            <span className="eyebrow">Не возьмёт никто</span>
            <span className="readout">{stuck}</span>
          </span>
        </div>

        {s.missing > 0 ? (
          <p className="text-[13px] text-ink-2">
            Сервис добавлял бригады по одной, пока каждая новая забирала хотя бы одну
            заявку. С ними день закроется на{' '}
            <span className="tnum font-semibold">{s.assigned}</span> заявках из{' '}
            <span className="tnum">{plan.metrics.orders_total}</span> вместо нынешних{' '}
            <span className="tnum">{plan.metrics.orders_assigned}</span>.
          </p>
        ) : (
          <p className="text-[13px] text-ink-2">
            Людей хватает: все заявки, которые вообще можно выполнить, уже разошлись.
          </p>
        )}

        {stuck > 0 ? (
          <p className="rounded-md border-l-2 border-warn bg-raised/60 px-3 py-2 text-[13px] text-ink">
            {s.reason || 'Эти заявки не берёт даже свободная бригада: мешает окно или требования заявки.'}
          </p>
        ) : null}

        <div className="flex flex-wrap gap-2 border-t border-line pt-3">
          <Button variant="primary" onClick={onShowUnassigned}>
            Показать заявки без исполнителя
          </Button>
          <Button onClick={onExport}>Выгрузить план с обоснованием</Button>
        </div>

        <p className="text-[12px] text-ink-3">
          Обоснование это тот же файл выгрузки: в нём есть каждая заявка, её бригада и
          причина по тем, что не разошлись.
        </p>
      </div>
    </Modal>
  );
}
