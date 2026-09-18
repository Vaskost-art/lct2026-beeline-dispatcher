import type { Meta } from '../../api/types';
import { Modal } from '../../components/Modal';

interface Props {
  meta: Meta | undefined;
  open: boolean;
  onClose: () => void;
}

/** Как считаем.

Всё, что мы придумали за отсутствующие в выгрузке данные, объявлено здесь:
диспетчер должен видеть, где кончаются его данные и начинается модель.
*/
export function AssumptionsDialog({ meta, open, onClose }: Props) {
  return (
    <Modal open={open} title="Как считаем" onClose={onClose}>
      <ul className="flex flex-col divide-y divide-line border-y border-line">
        {(meta?.assumptions ?? []).map((item) => (
          <li key={item.title} className="py-2">
            <h3 className="text-[13px] font-semibold">{item.title}</h3>
            <p className="mt-0.5 text-[13px] text-ink-2">{item.text}</p>
          </li>
        ))}
      </ul>
    </Modal>
  );
}
