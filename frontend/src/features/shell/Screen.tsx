import { MapTrifold, WarningOctagon } from '@phosphor-icons/react';

import { ApiError } from '../../api/client';
import { useMeta, usePlan, useRunPlan } from '../../api/queries';
import { useDay } from '../../state/day';
import { EventBar } from '../event/EventBar';
import { Header } from './Header';
import { Summary } from './Summary';
import { Workspace } from './Workspace';

/** Экран диспетчера целиком.

Расчёт сам не стартует: приглашение выбрать участок это состояние экрана, а
не мигание. Раньше расчёт начинался при открытии, и при недоступной карте
человек до сорока секунд смотрел в пустоту.
*/
export function Screen() {
  const day = useDay();
  const meta = useMeta();
  const plan = usePlan(day.region);
  const run = useRunPlan();

  const payload = plan.data;
  const notBuilt = plan.error instanceof ApiError && plan.error.code === 'plan_not_built';
  const failure = run.error ?? (notBuilt ? null : plan.error);

  return (
    <div className="flex h-full flex-col bg-page">
      <Header
        regions={meta.data?.regions ?? []}
        region={day.region}
        onRegion={day.selectRegion}
        onMenu={() => day.openPanel('menu')}
        onPlan={() => {
          if (day.region) run.mutate({ region: day.region, strategy: 'optimized' });
        }}
        busy={run.isPending}
        planned={Boolean(payload)}
      />

      {payload ? (
        <Summary
          plan={payload}
          stale={run.isPending}
          onShortfall={() => day.openPanel('shortfall')}
        />
      ) : null}

      <main className="flex min-h-0 flex-1 flex-col gap-3 p-3">
        {failure ? (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-lg border border-danger/30 bg-danger-soft px-3 py-2"
          >
            <WarningOctagon
              size={16}
              weight="fill"
              aria-hidden
              className="mt-0.5 shrink-0 text-danger"
            />
            <span className="text-[13px] text-ink">{(failure as ApiError).message}</span>
          </div>
        ) : null}

        {payload ? (
          <>
            <Workspace plan={payload} day={day} apiKey={meta.data?.map_api_key ?? ''} />
            <EventBar plan={payload} />
          </>
        ) : (
          <FirstRun region={day.region} loading={run.isPending || plan.isFetching} />
        )}
      </main>
    </div>
  );
}

/** Экран до первого плана: говорит, что это за место и какая кнопка его
    наполнит. Серая надпись «нет данных» такой работы не делает. */
function FirstRun({ region, loading }: { region: string | null; loading: boolean }) {
  return (
    <div className="flex min-h-0 flex-1 items-center justify-center rounded-lg border border-dashed border-line-2 bg-panel">
      <div className="flex max-w-[56ch] flex-col items-center gap-3 px-6 py-12 text-center">
        <MapTrifold size={28} weight="duotone" aria-hidden className="text-ink-4" />
        <h2 className="text-[15px] font-semibold tracking-[-0.01em]">
          {region ? 'План на сегодня ещё не построен' : 'Смена не выбрана'}
        </h2>
        <p className="text-[13px] text-ink-3">
          {loading
            ? 'Считаем маршруты. Это занимает до полутора десятков секунд.'
            : region
              ? 'Нажмите «Спланировать»: сервис разложит заявки по бригадам, покажет маршруты на карте и назовёт причину по каждой заявке, которая не поместилась.'
              : 'Выберите участок в шапке. Дальше одна кнопка: сервис соберёт маршруты и покажет, что осталось без исполнителя.'}
        </p>
      </div>
    </div>
  );
}
