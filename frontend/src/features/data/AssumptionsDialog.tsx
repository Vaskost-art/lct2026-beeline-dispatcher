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

      {/* Раньше все двенадцать допущений были свёрнуты: человек открывал окно
          «Как считаем» и не узнавал ни одного допущения. Текст каждого - две
          строки, прятать тут нечего. */}
      <ul className="flex flex-col divide-y divide-line border-y border-line">
        {(meta?.assumptions ?? []).map((item) => (
          <li key={item.title} className="py-2">
            <p className="text-[13px] font-medium">{item.title}</p>
            <p className="mt-0.5 max-w-[64ch] text-[13px] leading-relaxed text-ink-2">
              {item.text}
            </p>
          </li>
        ))}
      </ul>
    </Modal>
  );
}
