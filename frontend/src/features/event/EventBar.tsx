import { CaretDown, Lightning } from '@phosphor-icons/react';
import { useState } from 'react';

import { useReplan } from '../../api/queries';
import type { ApiError } from '../../api/client';
import type { PlanPayload } from '../../api/types';
import { Button } from '../../components/Button';
import { EMPTY_DRAFT, KIND_TITLES, toRequest, whatIsMissing, type EventDraft } from './draft';
import { EventFields } from './EventFields';
import { EventPreview } from './EventPreview';

interface Props {
  plan: PlanPayload;
}

/** Событие в течение дня.

Предпросмотр не трогает рабочий день: пока не нажато «Применить», на экране
предсказание, а план остаётся прежним. Считает предпросмотр и применение
одна и та же ручка сервиса, поэтому они не могут разойтись.
*/
export function EventBar({ plan }: Props) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<EventDraft>(EMPTY_DRAFT);
  const replan = useReplan();
  const preview = replan.data && !replan.data.applied ? replan.data : null;
  const applied = replan.data?.applied ? replan.data : null;
  const missing = whatIsMissing(draft);

  const change = (next: EventDraft) => {
    setDraft(next);
    // Прежний предпросмотр относится к прежним полям: оставлять его на
    // экране значит показывать предсказание не про то событие.
    replan.reset();
  };

  return (
    <section className="shrink-0 rounded-lg border border-line bg-panel">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex h-10 w-full items-center gap-2 px-3 text-left"
      >
        <Lightning size={15} weight="fill" aria-hidden className="text-accent" />
        <span className="text-[13px] font-medium">Событие в течение дня</span>
        <span className="truncate text-[12px] text-ink-3">
          срочная заявка, отмена, задержка или бригада выбыла
        </span>
        <CaretDown
          size={12}
          weight="bold"
          aria-hidden
          className={'ml-auto text-ink-4 transition-transform ' + (open ? 'rotate-180' : '')}
        />
      </button>

      {open ? (
        <div className="flex flex-col gap-3 border-t border-line px-3 py-3">
          <div
            role="group"
            aria-label="Вид события"
            className="inline-flex w-fit rounded-md border border-line bg-raised/60 p-0.5"
          >
            {KIND_TITLES.map(([kind, title]) => (
              <button
                key={kind}
                type="button"
                aria-pressed={draft.kind === kind}
                onClick={() => change({ ...EMPTY_DRAFT, kind, at: draft.at })}
                className={
                  'h-7 rounded-sm px-3 text-[12px] transition-colors duration-[120ms] ' +
                  (draft.kind === kind
                    ? 'bg-panel font-medium text-ink shadow-[0_1px_2px_rgb(10_14_20/0.08)]'
                    : 'text-ink-3 hover:text-ink')
                }
              >
                {title}
              </button>
            ))}
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <EventFields plan={plan} draft={draft} onChange={change} />
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-[13px] text-ink-2">
              <input
                type="checkbox"
                checked={draft.mode === 'full'}
                onChange={(event) =>
                  change({ ...draft, mode: event.target.checked ? 'full' : 'minimal' })
                }
              />
              Пересобрать остаток дня целиком
            </label>

            <Button
              variant="quiet"
              disabled={Boolean(missing)}
              busy={replan.isPending && !replan.variables?.apply}
              busyLabel="Считаем"
              onClick={() => replan.mutate(toRequest(draft, plan, false))}
            >
              Посмотреть, что изменится
            </Button>

            {missing ? <span className="text-[12px] text-ink-3">{missing}</span> : null}
          </div>

          {replan.error ? (
            <p role="alert" className="text-[13px] text-danger">
              {(replan.error as ApiError).message}
            </p>
          ) : null}

          {applied ? (
            <p className="rounded-md bg-ok-soft px-3 py-2 text-[13px] text-ink">
              Событие применено: план пересчитан. {applied.diff.event.description}
            </p>
          ) : null}

          {preview ? (
            <div className="flex flex-col gap-3 rounded-md border border-warn/35 bg-raised/50 px-3 py-2.5">
              <span className="text-[12px] font-medium text-warn">
                Предсказание. Рабочий день пока не изменился
              </span>
              <EventPreview before={plan} preview={preview} />
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="primary"
                  busy={replan.isPending && Boolean(replan.variables?.apply)}
                  busyLabel="Применяем"
                  onClick={() => replan.mutate(toRequest(draft, plan, true))}
                >
                  Применить к дню
                </Button>
                <Button variant="quiet" onClick={() => replan.reset()}>
                  Отказаться
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
