import { useCompare } from '../../api/queries';
import type { CompareRow } from '../../api/types';
import { Modal } from '../../components/Modal';

interface Props {
  region: string;
  open: boolean;
  onClose: () => void;
}

/** Подписи для человека, а не для разработчика: «то, что на экране» ничего
    не говорит тому, кто видит таблицу впервые. */
const ROW_MARK: Record<string, string> = {
  baseline: 'как раздают заявки без планировщика',
  greedy: 'простое правило: ближайшая подходящая бригада',
  optimized: 'наш план, он и показан на экране',
};

function Row({ row, best }: { row: CompareRow; best: boolean }) {
  const m = row.metrics;
  return (
    <tr className={best ? 'bg-ok-soft' : ''}>
      <td className="px-3 py-2 align-top">
        <p className="text-[13px] font-medium">{row.title}</p>
        <p className="text-[12px] text-ink-3">{ROW_MARK[row.key] ?? ''}</p>
      </td>
      <td className="px-3 py-2 text-right align-top text-[13px] font-semibold tnum">
        {m.orders_assigned}
        <span className="text-ink-4">/{m.orders_total}</span>
      </td>
      <td className="px-3 py-2 text-right align-top text-[13px] tnum">
        {m.used_engineers}
      </td>
      <td className="px-3 py-2 text-right align-top text-[13px] tnum">
        {m.total_km.toFixed(1)} <span className="unit">км</span>
      </td>
      <td className="px-3 py-2 text-right align-top text-[13px] tnum">
        {m.avg_km_per_order.toFixed(1)} <span className="unit">км</span>
      </td>
    </tr>
  );
}

/** Сравнение способов расчёта.

Базовый вариант задан в техническом задании дословно: заявки по порядку
поступления первому подходящему исполнителю. Он и отвечает на вопрос, зачем
здесь планировщик.
*/
export function CompareDialog({ region, open, onClose }: Props) {
  const compare = useCompare(region, open);
  const rows = compare.data?.rows ?? [];
  const baseline = rows.find((row) => row.key === 'baseline');
  const optimized = rows.find((row) => row.key === 'optimized');
  const greedy = rows.find((row) => row.key === 'greedy');

  return (
    <Modal open={open} title="Сравнение способов расчёта" onClose={onClose}>
      {compare.isPending ? (
        <p className="text-[13px] text-ink-3">
          Считаем три плана подряд. Это занимает около полуминуты.
        </p>
      ) : null}

      {compare.error ? (
        <p role="alert" className="text-[13px] text-danger">
          Не удалось посчитать сравнение. Постройте план и попробуйте снова.
        </p>
      ) : null}

      {compare.data ? (
        <>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] border-collapse">
              <thead>
                <tr className="border-b border-line text-left">
                  <th className="px-3 py-2 eyebrow">Способ</th>
                  <th className="px-3 py-2 text-right eyebrow">Заявок</th>
                  <th className="px-3 py-2 text-right eyebrow">Бригад</th>
                  <th className="px-3 py-2 text-right eyebrow">Пробег</th>
                  <th className="px-3 py-2 text-right eyebrow">На заявку</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {rows.map((row) => (
                  <Row key={row.key} row={row} best={row.key === 'optimized'} />
                ))}
              </tbody>
            </table>
          </div>

          {baseline && optimized && greedy ? (
            <div className="mt-4 flex flex-col gap-2 rounded-md border border-line bg-raised px-3 py-2">
              <p className="text-[13px] text-ink">
                <span className="font-semibold">Задача нетривиальна.</span> Честное
                последовательное распределение берёт{' '}
                <span className="tnum">{baseline.metrics.orders_assigned}</span> заявок из{' '}
                <span className="tnum">{baseline.metrics.orders_total}</span>: остальные не
                помещаются в окна и смены.
              </p>
              <p className="text-[13px] text-ink">
                <span className="font-semibold">Оптимизатор нужен.</span> Он делает ту же работу,
                что быстрая эвристика (
                <span className="tnum">{greedy.metrics.orders_assigned}</span> заявок), но берёт
                больше (<span className="tnum">{optimized.metrics.orders_assigned}</span>) и
                проезжает на{' '}
                <span className="tnum">
                  {Math.round(greedy.metrics.total_km - optimized.metrics.total_km)}
                </span>{' '}
                км меньше.
              </p>
              <p className="text-[12px] text-ink-3">{compare.data.basis}</p>
            </div>
          ) : null}
        </>
      ) : null}
    </Modal>
  );
}
