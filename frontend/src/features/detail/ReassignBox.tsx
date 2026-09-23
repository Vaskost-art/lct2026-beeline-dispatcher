import { useState } from 'react';

import { useReassign } from '../../api/queries';
import type { ApiError } from '../../api/client';
import type { Alternative } from '../../api/types';
import { Button } from '../../components/Button';
import { decimal } from '../../text';

interface Props {
  region: string;
  orderId: string;
  /** Бригада, у которой заявка сейчас; пусто, если заявка без исполнителя. */
  holder: string | undefined;
  crews: { id: string; name: string }[];
  /** Разбор «кто ещё мог взять»: по нему подходящие бригады идут первыми. */
  alternatives: Alternative[];
}

/** Передача заявки бригаде по решению диспетчера. */
export function ReassignBox({ region, orderId, holder, crews, alternatives }: Props) {
  const reassign = useReassign();
  // Выбор бригады и подтверждение разделены: список без кнопки не говорит,
  // применится ли решение и когда.
  const [picked, setPicked] = useState('');
  const known = new Map(alternatives.map((item) => [item.engineer_id, item]));
  const rank = (id: string) => {
    const item = known.get(id);
    return item ? (item.possible ? 0 : 2) : 1;
  };
  const options = crews
    .filter((crew) => crew.id !== holder)
    .sort((a, b) => rank(a.id) - rank(b.id));
  const title = holder ? 'Передать другой бригаде' : 'Назначить бригаде';
  // Разбор уже сказал, что ни одна бригада не берёт заявку: активная кнопка
  // вела бы в отказ, а причину диспетчер и так видит выше.
  const nobody = options.length > 0 && options.every((crew) => known.get(crew.id)?.possible === false);
  if (nobody) {
    return (
      <p className="text-[12px] text-ink-3">
        {holder ? 'Передать' : 'Назначить'} сейчас некому: ни одна бригада не успевает взять
        заявку, причины выше. Помогут другое окно клиента или ещё одна бригада.
      </p>
    );
  }

  if (reassign.isSuccess) {
    return (
      <p className="rounded-md bg-ok-soft px-2 py-1.5 text-[12px] text-ink">
        Заявка у бригады «{crews.find((crew) => crew.id === picked)?.name ?? picked}». Она
        закреплена и останется у неё при следующем пересчёте.
      </p>
    );
  }

  return (
    <>
      <span className="text-[12px] font-medium text-ink-3">{title}</span>
      <div className="mt-1 flex gap-2">
        <select
          aria-label={title}
          value={picked}
          onChange={(event) => setPicked(event.target.value)}
          className="h-8 min-w-0 flex-1 rounded-md border border-line bg-panel px-2 text-[13px]"
        >
          <option value="">Выберите бригаду</option>
          {options.map((crew) => {
            const item = known.get(crew.id);
            const note = !item
              ? ''
              : item.possible
                ? item.extra_km !== undefined
                  ? `, +${decimal(item.extra_km)} км`
                  : ''
                : ', не подходит';
            return (
              <option key={crew.id} value={crew.id}>
                {crew.name}
                {note}
              </option>
            );
          })}
        </select>
        <Button
          variant="primary"
          disabled={!picked}
          busy={reassign.isPending}
          busyLabel="Переносим"
          onClick={() => reassign.mutate({ region, order_id: orderId, engineer_id: picked })}
        >
          {holder ? 'Передать' : 'Назначить'}
        </Button>
      </div>
      {reassign.error ? (
        <p role="alert" className="mt-1.5 text-[12px] text-danger">
          {(reassign.error as ApiError).message}
        </p>
      ) : null}
    </>
  );
}
