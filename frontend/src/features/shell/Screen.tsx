import { MapTrifold, ShieldCheck, Timer, Toolbox, WarningOctagon } from '@phosphor-icons/react';

import { Button } from '../../components/Button';

import { ApiError } from '../../api/client';
import { useMeta, usePlan, useRunPlan } from '../../api/queries';
import type { RegionSummary } from '../../api/types';
import { useDay } from '../../state/day';
import { CompareDialog } from '../compare/CompareDialog';
import { AssumptionsDialog } from '../data/AssumptionsDialog';
import { UploadDialog } from '../data/UploadDialog';
import { ValidateDialog } from '../data/ValidateDialog';
import { EventBar } from '../event/EventBar';
import { PickupDialog } from '../pickup/PickupDialog';
import { RiskDialog } from '../risk/RiskDialog';
import { ShortfallDialog } from '../shortfall/ShortfallDialog';
import { Menu } from './Menu';
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
          actions={
            <>
              <Button onClick={() => day.openPanel('validate')}>
                <ShieldCheck size={15} weight="bold" aria-hidden />
                Проверить план
              </Button>
              <Button onClick={() => day.openPanel('risk')}>
                <Timer size={15} weight="bold" aria-hidden />
                Опоздания
              </Button>
              <Button onClick={() => day.openPanel('pickup')}>
                <Toolbox size={15} weight="bold" aria-hidden />
                Ведомость
              </Button>
            </>
          }
        />
      ) : null}

      <main
        className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-3 lg:overflow-hidden"
      >
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
          <FirstRun
            region={day.region}
            loading={run.isPending || plan.isFetching}
            regions={meta.data?.regions ?? []}
            onRegion={day.selectRegion}
            onPlan={() => {
              if (day.region) run.mutate({ region: day.region, strategy: 'optimized' });
            }}
            onUpload={() => day.openPanel('upload')}
          />
        )}
      </main>

      <Menu
        open={day.panel === 'menu'}
        region={day.region}
        planned={Boolean(payload)}
        theme={day.theme}
        onTheme={day.setTheme}
        onPanel={day.openPanel}
        onClose={day.closePanel}
      />

      <UploadDialog
        open={day.panel === 'upload'}
        onClose={day.closePanel}
        onLoaded={(region) => {
          day.closePanel();
          day.selectRegion(region);
        }}
      />

      <AssumptionsDialog
        meta={meta.data}
        open={day.panel === 'assumptions'}
        onClose={day.closePanel}
      />

      {day.region ? (
        <>
          <CompareDialog
            region={day.region}
            open={day.panel === 'compare'}
            onClose={day.closePanel}
          />
          <ValidateDialog
            region={day.region}
            open={day.panel === 'validate'}
            onClose={day.closePanel}
          />
        </>
      ) : null}

      {payload ? (
        <>
          <RiskDialog plan={payload} open={day.panel === 'risk'} onClose={day.closePanel} />
          <PickupDialog plan={payload} open={day.panel === 'pickup'} onClose={day.closePanel} />
          <ShortfallDialog
            plan={payload}
            open={day.panel === 'shortfall'}
            onClose={day.closePanel}
          />
        </>
      ) : null}
    </div>
  );
}

/** Экран до первого плана: говорит, что это за место, и даёт действие.
    Серая надпись «нет данных» такой работы не делает. */
function FirstRun({
  region,
  loading,
  regions,
  onRegion,
  onPlan,
  onUpload,
}: {
  region: string | null;
  loading: boolean;
  regions: RegionSummary[];
  onRegion: (region: string) => void;
  onPlan: () => void;
  onUpload: () => void;
}) {
  return (
    <div className="flex min-h-0 flex-1 items-center justify-center rounded-lg border border-line bg-panel">
      <div className="flex w-full max-w-[44ch] flex-col items-center gap-4 px-6 py-12 text-center">
        <MapTrifold size={32} weight="duotone" aria-hidden className="text-ink-4" />
        <h2 className="text-[17px] font-semibold tracking-[-0.015em]">
          {region ? 'План на сегодня ещё не построен' : 'Смена не выбрана'}
        </h2>
        <p className="text-[13px] leading-relaxed text-ink-3">
          {loading
            ? 'Считаем маршруты. Это занимает несколько секунд.'
            : region
              ? 'Сервис разложит заявки по бригадам, покажет маршруты на карте и назовёт причину по каждой заявке, которая не поместилась.'
              : 'Возьмите участок из выгрузки организаторов или загрузите свой файл с заявками.'}
        </p>

        {region ? (
          <Button variant="primary" onClick={onPlan} busy={loading}>
            Спланировать день
          </Button>
        ) : (
          <div className="flex w-full flex-col gap-2">
            {regions.map((item) => (
              <Button key={item.region_key} onClick={() => onRegion(item.region_key)}>
                <span className="flex-1 text-left">{item.region_name}</span>
                <span className="text-[12px] text-ink-3 tnum">
                  {item.orders} заявок · {item.engineers} бригад
                </span>
              </Button>
            ))}
            <Button variant="quiet" onClick={onUpload}>
              Загрузить свой набор данных
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
