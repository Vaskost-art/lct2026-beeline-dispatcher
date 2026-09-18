import { useMeta, usePlan, useRunPlan } from '../../api/queries';
import { ApiError } from '../../api/client';
import { useDay } from '../../state/day';
import { MapView } from '../map/MapView';
import { WorkList } from '../routes/WorkList';
import { Header } from './Header';
import { Metrics } from './Metrics';

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

  return (
    <div className="flex h-full flex-col">
      <Header
        regions={meta.data?.regions ?? []}
        region={day.region}
        onRegion={day.selectRegion}
        onMenu={() => day.openPanel('menu')}
        onPlan={() => {
          if (day.region) run.mutate({ region: day.region, strategy: 'optimized' });
        }}
        busy={run.isPending}
      />

      {payload ? (
        <Metrics plan={payload} stale={run.isPending} onShortfall={() => day.openPanel('shortfall')} />
      ) : null}

      <main className="flex min-h-0 flex-1 flex-col gap-3 p-4">
        {!day.region ? (
          <p className="text-muted">
            Выберите участок в шапке и нажмите «Спланировать»: сервис соберёт маршруты
            и покажет, что осталось без исполнителя.
          </p>
        ) : null}

        {day.region && !payload && notBuilt ? (
          <p className="text-muted">План ещё не построен. Нажмите «Спланировать».</p>
        ) : null}

        {plan.error && !notBuilt ? (
          <p role="alert" className="text-danger">
            {(plan.error as ApiError).message}
          </p>
        ) : null}

        {run.error ? (
          <p role="alert" className="text-danger">
            {(run.error as ApiError).message}
          </p>
        ) : null}

        {payload ? (
          <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
            <WorkList plan={payload} selected={day.selectedOrder} onSelect={day.selectOrder} />
            <MapView
              plan={payload}
              hiddenCrews={day.hiddenCrews}
              selected={day.selectedOrder}
              apiKey={meta.data?.map_api_key ?? ''}
              theme={day.theme}
              onSelect={day.selectOrder}
            />
          </div>
        ) : null}
      </main>
    </div>
  );
}
