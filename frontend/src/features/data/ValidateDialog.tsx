import { CheckCircle, WarningOctagon } from '@phosphor-icons/react';

import { useValidation } from '../../api/queries';
import { Modal } from '../../components/Modal';

interface Props {
  region: string;
  open: boolean;
  onClose: () => void;
}

/** Независимая проверка плана: правила проверяются заново, не тем кодом,
    который строил план. */
export function ValidateDialog({ region, open, onClose }: Props) {
  const check = useValidation(region, open);
  const report = check.data;

  return (
    <Modal open={open} title="Проверка плана" onClose={onClose}>
      {check.isPending ? <p className="text-[13px] text-ink-3">Проверяем маршруты…</p> : null}

      {report ? (
        <div className="flex flex-col gap-3">
          <p
            className={
              'flex items-center gap-2 rounded-md px-3 py-2 text-[13px] ' +
              (report.ok ? 'bg-ok-soft' : 'bg-danger-soft')
            }
          >
            {report.ok ? (
              <CheckCircle size={18} weight="fill" aria-hidden className="text-ok" />
            ) : (
              <WarningOctagon size={18} weight="fill" aria-hidden className="text-danger" />
            )}
            {report.ok
              ? `Нарушений нет: проверено ${report.checked_stops} визитов в ${report.checked_routes} маршрутах.`
              : `Найдены нарушения: ${report.violations.length}.`}
          </p>

          {report.violations.length > 0 ? (
            <ul className="flex flex-col divide-y divide-line border-y border-line">
              {report.violations.map((item, index) => (
                <li key={`${item.rule}-${index}`} className="py-2 text-[13px]">
                  <span className="eyebrow">{item.rule}</span>
                  <p className="text-ink-2">{item.text}</p>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </Modal>
  );
}
