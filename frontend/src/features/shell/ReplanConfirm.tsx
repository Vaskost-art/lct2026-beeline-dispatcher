import { Button } from '../../components/Button';
import { Modal } from '../../components/Modal';
import { plural } from '../../text';

interface Props {
  open: boolean;
  /** Что именно будет отменено: подписи применённых за день изменений. */
  changes: string[];
  onCancel: () => void;
  onConfirm: () => void;
}

/** Подтверждение повторного расчёта.

Пересчёт собирает день заново из исходных заявок, то есть отменяет всё, что
диспетчер применил за смену: переданные вручную заявки, разобранные события,
закрепления. Одно нажатие в углу экрана не должно этого делать молча.
*/
export function ReplanConfirm({ open, changes, onCancel, onConfirm }: Props) {
  return (
    <Modal open={open} title="Собрать день заново?" onClose={onCancel}>
      <p className="text-[13px] text-ink">
        Расчёт начнётся с исходных заявок участка. {changes.length}{' '}
        {plural(changes.length, 'изменение', 'изменения', 'изменений')}, применённых
        за смену, будут отменены:
      </p>

      <ul className="mt-2 flex flex-col gap-1">
        {changes.map((change, index) => (
          <li
            key={`${change}-${index}`}
            className="rounded-md border border-line bg-raised px-2 py-1 text-[12px] text-ink-2"
          >
            {change}
          </li>
        ))}
      </ul>

      <div className="mt-4 flex justify-end gap-2">
        <Button onClick={onCancel}>Оставить как есть</Button>
        <Button variant="primary" onClick={onConfirm}>
          Собрать заново
        </Button>
      </div>
    </Modal>
  );
}
