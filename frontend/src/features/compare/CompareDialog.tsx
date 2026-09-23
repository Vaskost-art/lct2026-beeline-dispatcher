import { useCompare } from '../../api/queries';
import type { CompareRow } from '../../api/types';
import { Modal } from '../../components/Modal';
import { decimal, plural } from '../../text';

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
        <p className="text-[11px] text-ink-3">{row.method}</p>
      </td>
      <td className="px-3 py-2 text-right align-top text-[13px] font-semibold tnum">
        {m.orders_assigned}
        <span className="text-ink-3">/{m.orders_total}</span>
      </td>
      <td className="px-3 py-2 text-right align-top text-[13px] tnum">
        {m.used_engineers}
      </td>
      <td className="px-3 py-2 text-right align-top text-[13px] tnum">
        {decimal(m.total_km)} <span className="unit">км</span>
      </td>
      <td className="px-3 py-2 text-right align-top text-[13px] tnum">
        {decimal(m.avg_km_per_order)} <span className="unit">км</span>
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
  const saved =
    optimized && greedy ? Math.round(greedy.metrics.total_km - optimized.metrics.total_km) : 0;

  return (
    <Modal open={open} title="Сравнение способов расчёта" onClose={onClose}>
      {compare.isPending ? (
        <p className="text-[13px] text-ink-3">
          Считаем три плана подряд теми же настройками, что и план на экране: это занимает одну-две минуты. Быстрее нельзя - иначе расчёт остановят на полпути и сравнение выйдет нечестным.
        </p>
      ) : null}

      {compare.error ? (
        <p role="alert" className="text-[13px] text-danger">
          Не удалось посчитать сравнение. Постройте план и попробуйте снова.
        </p>
      ) : null}

      {compare.data ? (
        <>
          {compare.data.changed ? (
            <p className="mb-2 rounded-md border border-warn/40 bg-warn-soft px-3 py-2 text-[12px] text-ink">
              К плану на экране уже применены события дня, поэтому его числа
              отличаются от строки «наш план»: все три способа посчитаны по
              исходному дню участка. Иначе сравнение шло бы на разных наборах
              заявок.
            </p>
          ) : null}

          <p className="mb-1 text-[11px] text-ink-3 sm:hidden">
            Таблицу можно прокрутить вбок
          </p>
          <div className="overflow-x-auto rounded-md border border-line">
            <table className="w-full min-w-[560px] border-collapse">
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

          {/* Первый вопрос к таблице - «а с чем вы сравниваете». Отвечаем
              сразу: колонки исполнителя в выгрузке нет, поэтому точкой
              отсчёта служит вариант, заданный техническим заданием. */}
          <p className="mt-3 text-[12px] leading-relaxed text-ink-3">
            В выгрузке организаторов нет колонки исполнителя: все{' '}
            <span className="tnum">{optimized?.metrics.orders_total ?? ''}</span> заявок
            в ней без бригады. Поэтому точка отсчёта - базовый вариант, заданный
            техническим заданием дословно: заявки по порядку поступления первому
            подходящему исполнителю.
          </p>

          {baseline && optimized && greedy ? (
            <div className="mt-4 flex flex-col gap-2 rounded-md border border-line bg-raised px-3 py-2">
              <p className="text-[13px] text-ink">
                <span className="font-semibold">Задача нетривиальна.</span> Честное
                последовательное распределение берёт{' '}
                <span className="tnum">{baseline.metrics.orders_assigned}</span> из{' '}
                <span className="tnum">{baseline.metrics.orders_total}</span>{' '}
                {plural(baseline.metrics.orders_total, 'заявки', 'заявок', 'заявок')}: при таком
                порядке остальные не помещаются в окна клиентов и смены бригад.
              </p>
              <p className="text-[13px] text-ink">
                <span className="font-semibold">Перебор вариантов окупается.</span> Быстрый
                расчёт по простому правилу берёт{' '}
                <span className="tnum">{greedy.metrics.orders_assigned}</span>{' '}
                {plural(greedy.metrics.orders_assigned, 'заявку', 'заявки', 'заявок')}, полный
                расчёт <span className="tnum">{optimized.metrics.orders_assigned}</span>
                {saved > 0 ? (
                  <>
                    {' '}и проезжает на <span className="tnum">{saved}</span> км меньше
                  </>
                ) : null}
                .
              </p>
              {compare.data.changed ? null : (
                <p className="text-[12px] text-ink-3">{compare.data.basis}</p>
              )}
            </div>
          ) : null}
        </>
      ) : null}
    </Modal>
  );
}
