import { useState } from 'react';

import type { ApiError } from '../../api/client';
import { useEquipmentTransfer } from '../../api/queries';
import type { PlanPayload } from '../../api/types';
import { Button } from '../../components/Button';
import { Modal } from '../../components/Modal';
import { plural } from '../../text';

interface Props {
  plan: PlanPayload;
  open: boolean;
  onClose: () => void;
}

/** Ведомость на выдачу и передача оборудования между бригадами.

Ведомость показывает выданное утром, а не расчёт по текущему плану: бригада
уехала с этой сумкой, и днём заявку она возьмёт только под то, что с собой.
Передача закрывает тупик - устройство можно отдать соседу, если оно не
расписано под собственные заявки.
*/
export function PickupDialog({ plan, open, onClose }: Props) {
  const total = plan.pickup.reduce((sum, row) => sum + row.total, 0);
  const move = useEquipmentTransfer();
  const [source, setSource] = useState('');
  const [target, setTarget] = useState('');
  const [item, setItem] = useState('');

  const items = Array.from(
    new Set(plan.pickup.flatMap((row) => Object.keys(row.items))),
  );
  const ready = source && target && item && source !== target;

  return (
    <Modal open={open} title="Что взять в офисе" onClose={onClose}>
      {plan.pickup.length === 0 ? (
        <p className="text-[13px] text-ink-3">
          По этому плану везти нечего: все работы без установки оборудования.
        </p>
      ) : (
        <>
          <p className="mb-3 text-[13px] text-ink-2">
            Выдано <span className="font-semibold tnum">{total}</span>{' '}
            {plural(total, 'устройство', 'устройства', 'устройств')} на{' '}
            <span className="tnum">{plan.pickup.length}</span>{' '}
            {plural(plan.pickup.length, 'бригаду', 'бригады', 'бригад')}, включая запас.
          </p>
          <ul className="flex flex-col divide-y divide-line border-y border-line">
            {plan.pickup.map((row) => (
              // На телефоне состав уходит строкой под имя бригады: в одну
              // строку имя обрезалось до «Бр…», а по нему и звонят.
              <li
                key={row.engineer_id}
                className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 py-2"
              >
                <span className="min-w-0 flex-1 whitespace-nowrap text-[13px] font-medium">
                  {row.engineer_id}
                </span>
                <span className="order-last basis-full text-[13px] text-ink-2 sm:order-none sm:basis-auto">
                  {row.text}
                </span>
                <span className="w-10 text-right text-[13px] font-semibold tnum">{row.total}</span>
              </li>
            ))}
          </ul>

          <div className="mt-4 border-t border-line pt-3">
            <p className="text-[12px] font-medium text-ink-3">Передать между бригадами</p>
            <p className="mt-0.5 text-[12px] text-ink-3">
              Отдать можно только свободное: под свои заявки устройство остаётся у бригады.
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <select
                aria-label="От бригады"
                value={source}
                onChange={(event) => setSource(event.target.value)}
                className="h-8 min-w-0 flex-1 rounded-md border border-line bg-panel px-2 text-[13px]"
              >
                <option value="">От кого</option>
                {plan.pickup.map((row) => (
                  <option key={row.engineer_id} value={row.engineer_id}>
                    {row.engineer_id}
                  </option>
                ))}
              </select>
              <select
                aria-label="Кому"
                value={target}
                onChange={(event) => setTarget(event.target.value)}
                className="h-8 min-w-0 flex-1 rounded-md border border-line bg-panel px-2 text-[13px]"
              >
                <option value="">Кому</option>
                {plan.engineers
                  .filter((engineer) => engineer.id !== source)
                  .map((engineer) => (
                    <option key={engineer.id} value={engineer.id}>
                      {engineer.name}
                    </option>
                  ))}
              </select>
              <select
                aria-label="Что передать"
                value={item}
                onChange={(event) => setItem(event.target.value)}
                className="h-8 min-w-0 flex-1 rounded-md border border-line bg-panel px-2 text-[13px]"
              >
                <option value="">Что</option>
                {items.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
              <Button
                variant="primary"
                disabled={!ready}
                busy={move.isPending}
                busyLabel="Передаём"
                onClick={() =>
                  move.mutate({ region: plan.region, source, target, item, count: 1 })
                }
              >
                Передать
              </Button>
            </div>
            {move.error ? (
              <p role="alert" className="mt-1.5 text-[12px] text-danger">
                {(move.error as ApiError).message}
              </p>
            ) : null}
            {move.isSuccess && !move.error ? (
              <p className="mt-1.5 text-[12px] text-ok">Передано. Ведомость обновлена.</p>
            ) : null}
          </div>
        </>
      )}
    </Modal>
  );
}
