import type { PlanPayload } from '../../api/types';
import { crewColor } from './model';

interface Props {
  plan: PlanPayload | undefined;
  hiddenCrews: Set<string>;
  onToggleCrew: (crew: string) => void;
}

/** Легенда карты.

Первый вопрос к схеме - что означают цвета, а означают они бригады. Пока
легенда объясняла только формы, восемь цветных маршрутов оставались без
подписи, а серый кружок «визит бригады» рядом с цветными точками сбивал с
толку.

Строка бригады ещё и выключает её маршрут: на схеме из восьми маршрутов
разобрать один иначе нечем.
*/
export function MapLegend({ plan, hiddenCrews, onToggleCrew }: Props) {
  const crews = (plan?.routes ?? [])
    .map((route, index) => ({
      id: route.engineer_id,
      color: crewColor(index),
      name:
        plan?.engineers.find((engineer) => engineer.id === route.engineer_id)?.name ??
        route.engineer_id,
      stops: route.stops.length,
    }))
    .filter((crew) => crew.stops > 0);

  // Легенда лежит поверх подписей районов: те подняты над маркерами, иначе
  // кружки визитов перечёркивают названия, а легенда должна быть выше обоих.
  return (
    <div
      className="absolute bottom-3 right-3 z-10 flex max-h-[58%] w-[132px] flex-col gap-0.5
                 overflow-auto rounded-md border border-line bg-panel/95 px-2 py-1.5
                 text-[11px] text-ink-3 backdrop-blur-[1px]"
    >
      {crews.length > 0 ? (
        <>
          <span className="font-semibold uppercase tracking-[0.05em] text-ink-4">
            Бригады
          </span>
          {crews.map((crew) => {
            const hidden = hiddenCrews.has(crew.id);
            return (
              <button
                key={crew.id}
                type="button"
                aria-pressed={!hidden}
                onClick={() => onToggleCrew(crew.id)}
                className={
                  'flex items-center gap-1.5 rounded-sm px-0.5 text-left ' +
                  'transition-colors duration-[120ms] hover:bg-raised ' +
                  (hidden ? 'opacity-45' : '')
                }
              >
                <span
                  aria-hidden
                  className="size-2.5 shrink-0 rounded-full"
                  style={{ background: hidden ? 'transparent' : crew.color,
                           boxShadow: `inset 0 0 0 1.5px ${crew.color}` }}
                />
                <span className="min-w-0 flex-1 truncate text-ink-2">{crew.name}</span>
                <span className="shrink-0 text-ink-4 tnum">{crew.stops}</span>
              </button>
            );
          })}
        </>
      ) : null}

      <span className="mt-0.5 flex items-center gap-1.5 border-t border-line pt-1">
        <span aria-hidden className="size-2.5 rotate-45 rounded-[2px] bg-ink-4" />
        старт из офиса
      </span>
      <span className="flex items-center gap-1.5">
        <span aria-hidden className="size-2.5 rotate-45 rounded-[2px] bg-danger" />
        без исполнителя
      </span>
    </div>
  );
}
