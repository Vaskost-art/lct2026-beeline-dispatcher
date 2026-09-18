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
      <p className="mb-3 max-w-[64ch] text-[13px] text-ink-2">
        Этих данных нет в выгрузке, и мы их достроили. Если какое-то допущение
        расходится с вашей практикой, скажите: оно настраивается и план пересчитается.
      </p>

      <ul className="flex flex-col divide-y divide-line border-y border-line">
        {(meta?.assumptions ?? []).map((item) => (
          <li key={item.title}>
            <details className="group py-2 [&>summary]:list-none [&>summary::-webkit-details-marker]:hidden">
              <summary className="cursor-pointer list-none text-[13px] font-medium">
                <span className="text-ink-4 group-open:hidden">▸ </span>
                <span className="hidden text-ink-4 group-open:inline">▾ </span>
                {item.title}
              </summary>
              <p className="mt-1 max-w-[64ch] pl-4 text-[13px] leading-relaxed text-ink-2">
                {item.text}
              </p>
            </details>
          </li>
        ))}
      </ul>
    </Modal>
  );
}
