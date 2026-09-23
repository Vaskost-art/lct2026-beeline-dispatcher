import type { PlanPayload } from '../../api/types';
import { plural } from '../../text';

interface Props {
  plan: PlanPayload;
  onUnassigned: () => void;
}

/** Бригады без единой заявки.

Раньше они молча пропадали из списка, и рядом с «не хватает бригад» это
читалось как ошибка планировщика: своя бригада свободна, а людей мало.
*/
export function IdleCrews({ plan, onUnassigned }: Props) {
  const idle = plan.routes
    .filter((route) => route.stops.length === 0)
    .map((route) => plan.engineers.find((engineer) => engineer.id === route.engineer_id))
    .filter((engineer) => engineer !== undefined);
  if (idle.length === 0) return null;

  const left = plan.unassigned.length;
  return (
    <div className="border-t border-line px-3 py-2 text-[12px] text-ink-2">
      <p>
        <span className="font-medium text-ink">
          {idle.length === 1 ? 'Свободна весь день' : 'Свободны весь день'}:
        </span>{' '}
        {idle
          .map(
            (engineer) =>
              `${engineer.name} (${engineer.vehicle === 'Автомобиль' ? 'с машиной' : 'без машины'})`,
          )
          .join(', ')}
        .
      </p>
      {left > 0 ? (
        <p className="mt-1 text-ink-3">
          Ни одну из {left} {plural(left, 'заявки', 'заявок', 'заявок')} без исполнителя{' '}
          {idle.length === 1 ? 'она не может взять' : 'они не могут взять'}: почему,{' '}
          <button
            type="button"
            onClick={onUnassigned}
            className="font-medium text-ink underline underline-offset-2"
          >
            написано в причинах
          </button>
          .
        </p>
      ) : (
        <p className="mt-1 text-ink-3">Все заявки разошлись и без них.</p>
      )}
    </div>
  );
}
