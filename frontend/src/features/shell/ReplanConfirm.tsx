import { Button } from '../../components/Button';
import { Modal } from '../../components/Modal';
import { plural } from '../../text';

interface Props {
  open: boolean;
  /** Решения, принятые за смену: они сохранятся, а маршруты пересоберутся. */
  changes: string[];
  onCancel: () => void;
  onConfirm: () => void;
}

/** Подтверждение повторного расчёта.

Пересчёт посреди смены сохраняет всё, что диспетчер применил: события,
закрепления, отметки хода работ. Меняются сами маршруты, и бригадам,
возможно, придётся звонить: об этом и спрашиваем.
*/
export function ReplanConfirm({ open, changes, onCancel, onConfirm }: Props) {
  return (
    <Modal open={open} title="Собрать день заново?" onClose={onCancel}>
      <p className="text-[13px] text-ink">
        Маршруты соберутся заново. {changes.length}{' '}
        {plural(changes.length, 'решение', 'решения', 'решений')} за смену останутся в силе,
        но визиты могут перейти к другим бригадам и сдвинуться по времени:
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
