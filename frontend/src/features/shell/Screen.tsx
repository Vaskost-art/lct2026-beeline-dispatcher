import {
  ArrowUUpLeft,
  ShieldCheck,
  Timer,
  Toolbox,
  WarningOctagon,
} from '@phosphor-icons/react';
import { useState } from 'react';

import { Button } from '../../components/Button';

import { ApiError } from '../../api/client';
import { useMeta, usePlan, useRunPlan, useUndo } from '../../api/queries';
import { useDay } from '../../state/day';
import { EventBar } from '../event/EventBar';
import { Menu } from './Menu';
import { ReplanConfirm } from './ReplanConfirm';
import { Decisions } from './Decisions';
import { Dialogs } from './Dialogs';
import { FirstRun } from './FirstRun';
import { Header } from './Header';
import { Summary } from './Summary';
import { Workspace } from './Workspace';

/** Экран диспетчера целиком.

Расчёт сам не стартует: приглашение выбрать участок это состояние экрана, а
не мигание: расчёт при открытии заставил бы человека смотреть в пустоту
до минуты.
*/
export function Screen() {
  const day = useDay();
  const meta = useMeta();
  const plan = usePlan(day.region);
  const run = useRunPlan();
  const undo = useUndo();

  const payload = plan.data;
  // Подтверждение перечисляет решения человека, а не всю историю: пересчёты
  // в ней тоже лежат, и строки «Пересчёт: оптимальный план» там шум.
  const applied = payload?.manual_changes ?? [];
  const history = payload?.undo ?? [];
  const [confirmReplan, setConfirmReplan] = useState(false);

  const startPlan = () => {
    if (!day.region) return;
    run.mutate({ region: day.region, strategy: 'optimized' });
  };
  // Время последнего ответа сервиса, а не сборки плана: отметка статуса
  // тоже обновляет данные, и подпись «собран» в этот момент врала бы.
  const builtAt = plan.dataUpdatedAt
    ? new Date(plan.dataUpdatedAt).toLocaleTimeString('ru-RU', {
        hour: '2-digit',
        minute: '2-digit',
      })
    : '';
  const notBuilt = plan.error instanceof ApiError && plan.error.code === 'plan_not_built';
  const failure = run.error ?? undo.error ?? (notBuilt ? null : plan.error);

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

        {/* Для встроенных участков адреса точные, а у загруженного файла
            километры могут быть оценкой: человек должен это видеть. */}
        {payload && payload.geo.level !== 'ok' ? (
          <p className="rounded-lg border border-warn/30 bg-warn-soft px-3 py-2 text-[12px] text-ink">
            {payload.geo.text}
          </p>
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
        journal={meta.data?.journal}
        theme={day.theme}
        onTheme={day.setTheme}
        onPanel={day.openPanel}
        onClose={day.closePanel}
        undoLabel={history[0]}
        onUndo={() => {
          if (day.region) undo.mutate({ region: day.region });
        }}
      />

      <Dialogs day={day} meta={meta.data} plan={payload} />
    </div>
  );
}
