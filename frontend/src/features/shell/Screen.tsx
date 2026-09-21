import {
  ArrowUUpLeft,
  MapTrifold,
  ShieldCheck,
  Timer,
  Toolbox,
  WarningOctagon,
} from '@phosphor-icons/react';
import { useState } from 'react';

import { Button } from '../../components/Button';

import { ApiError } from '../../api/client';
import { useMeta, usePlan, useRunPlan, useUndo } from '../../api/queries';
import type { RegionSummary } from '../../api/types';
import { useDay } from '../../state/day';
import { CompareDialog } from '../compare/CompareDialog';
import { AssumptionsDialog } from '../data/AssumptionsDialog';
import { UploadDialog } from '../data/UploadDialog';
import { EventBar } from '../event/EventBar';
import { ValidateDialog } from '../data/ValidateDialog';
import { PickupDialog } from '../pickup/PickupDialog';
import { RiskDialog } from '../risk/RiskDialog';
import { ShortfallDialog } from '../shortfall/ShortfallDialog';
import { Menu } from './Menu';
import { ReplanConfirm } from './ReplanConfirm';
import { Decisions } from './Decisions';
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
  const undo = useUndo();

  const payload = plan.data;
  // Пересчёт отменяет решения человека, а не саму историю: сами пересчёты в
  // ней тоже лежат, и подтверждение показывало десяток строк «Пересчёт:
  // оптимальный план», которые терять не жалко.
  const applied = payload?.manual_changes ?? [];
  const history = payload?.undo ?? [];
  const [confirmReplan, setConfirmReplan] = useState(false);

  const startPlan = () => {
    if (!day.region) return;
    run.mutate({ region: day.region, strategy: 'optimized' });
  };
  // Время берётся у самого ответа: сервис не присылает момент сборки, а без
  // него свежий план не отличить от того, что лежит с утра.
  const builtAt = plan.dataUpdatedAt
    ? new Date(plan.dataUpdatedAt).toLocaleTimeString('ru-RU', {
        hour: '2-digit',
        minute: '2-digit',
      })
    : '—';
  const notBuilt = plan.error instanceof ApiError && plan.error.code === 'plan_not_built';
  const failure = run.error ?? (notBuilt ? null : plan.error);

  return (
    <div className="flex h-full flex-col bg-page">
      <Header
        regions={meta.data?.regions ?? []}
        region={day.region}
        onRegion={day.selectRegion}
        onMenu={() => day.openPanel('menu')}
        onPlan={() => (applied.length > 0 ? setConfirmReplan(true) : startPlan())}
        busy={run.isPending}
        planned={Boolean(payload)}
      />

      {payload ? (
        <Summary
          plan={payload}
          stale={run.isPending}
          builtAt={builtAt}
          actions={
            <>
              {/* Шаг назад появляется, только когда есть что отменять, и
                  называет последнее действие: за смену правок десятки, и
                  без отката ошибку можно исправить лишь пересчётом дня. */}
              {history.length > 0 ? (
                <Button
                  busy={undo.isPending}
                  busyLabel="Отменяем"
                  title={`Отменить: ${history[0]}`}
                  onClick={() => {
                    if (day.region) undo.mutate({ region: day.region });
                  }}
                >
                  <ArrowUUpLeft size={15} weight="bold" aria-hidden />
                  Шаг назад
                </Button>
              ) : null}
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
        className="relative flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-3 lg:overflow-hidden"
      >
        {payload ? (
          <Decisions
            plan={payload}
            onUnassigned={day.showUnassigned}
            onRisk={() => day.openPanel('risk')}
            onShortfall={() => day.openPanel('shortfall')}
          />
        ) : null}

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
            <EventBar plan={payload} onSelectOrder={day.selectOrder} />
          </>
        ) : (
          <FirstRun
            region={day.region}
            loading={run.isPending || plan.isFetching}
            regions={meta.data?.regions ?? []}
            onRegion={day.selectRegion}
            onPlan={startPlan}
            onUpload={() => day.openPanel('upload')}
          />
        )}
      </main>

      <ReplanConfirm
        open={confirmReplan}
        changes={applied}
        onCancel={() => setConfirmReplan(false)}
        onConfirm={() => {
          setConfirmReplan(false);
          startPlan();
        }}
      />

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
            onShowUnassigned={day.closePanel}
            onExport={() => {
              if (day.region) window.open(`/api/export/${day.region}`, '_blank');
            }}
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
  const current = regions.find((item) => item.region_key === region);

  return (
    <div className="flex min-h-0 flex-1 justify-center rounded-lg border border-line bg-panel pt-[12vh]">
      <div className="flex w-full max-w-[44ch] flex-col items-center gap-4 px-6 py-12 text-center">
        <MapTrifold size={32} weight="duotone" aria-hidden className="text-ink-3" />
        <h2 className="text-[17px] font-semibold tracking-[-0.015em]">
          {/* Во время расчёта заголовок «не построен» врёт: план как раз
              строится. Съёмка ловила эту надпись и снимала уже готовый план. */}
          {loading
            ? 'Считаем план на день'
            : region
              ? 'План на сегодня ещё не построен'
              : 'Смена не выбрана'}
        </h2>
        <p className="text-[13px] leading-relaxed text-ink-3">
          {loading
            ? 'Перебираем варианты: разложить сотню заявок по бригадам так, чтобы '
                + 'сошлись окна клиентов и смены, занимает от сорока секунд до двух минут.'
            : region
              ? 'Сервис разложит заявки по бригадам, покажет маршруты на карте и назовёт причину по каждой заявке, которая не поместилась.'
              : 'Возьмите участок из выгрузки организаторов или загрузите свой файл с заявками.'}
        </p>

        {/* Что сервис берёт в работу. Пустой экран перед расчётом - первое,
            что видит человек, и он должен видеть свой день, а не приглашение
            нажать кнопку. */}
        {current && !loading ? (
          <dl className="flex w-full flex-wrap justify-center gap-x-8 gap-y-3 rounded-md
                         border border-line bg-raised px-4 py-3 text-left">
            {[
              ['Заявок на день', current.orders],
              ['Бригад на участке', current.engineers],
              ['Срочных', current.urgent],
            ].map(([title, value]) => (
              <div key={String(title)} className="flex min-w-0 flex-col">
                <dt className="eyebrow">{title}</dt>
                <dd className="text-[20px] font-semibold leading-tight tnum">{value}</dd>
              </div>
            ))}
          </dl>
        ) : null}

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
