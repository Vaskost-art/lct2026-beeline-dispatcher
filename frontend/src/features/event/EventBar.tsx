import { CaretDown, Lightning } from '@phosphor-icons/react';
import { useState } from 'react';

import { useReplan } from '../../api/queries';
import type { ApiError } from '../../api/client';
import type { PlanPayload } from '../../api/types';
import { Button } from '../../components/Button';
import { EMPTY_DRAFT, toRequest, whatIsMissing, type EventDraft } from './draft';
import { EventFields } from './EventFields';
import { KindPicker } from './KindPicker';
import { EventPreview } from './EventPreview';

interface Props {
  plan: PlanPayload;
  /** Переход к заявке из предпросмотра последствий. */
  onSelectOrder: (orderId: string) => void;
}

/** Событие в течение дня.

Предпросмотр не трогает рабочий день: пока не нажато «Применить», на экране
предпросмотр, а план остаётся прежним. Считает предпросмотр и применение
одна и та же ручка сервиса, поэтому они не могут разойтись.
*/
export function EventBar({ plan, onSelectOrder }: Props) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<EventDraft>(EMPTY_DRAFT);
  const replan = useReplan();
  const preview = replan.data && !replan.data.applied ? replan.data : null;
  const applied = replan.data?.applied ? replan.data : null;
  const missing = whatIsMissing(draft);

  const change = (next: EventDraft) => {
    setDraft(next);
    // Прежний предпросмотр относится к прежним полям: оставлять его на
    // экране значит показывать последствия не того события.
    replan.reset();
  };

  return (
    <section
      className={
        // @container: раскрытая форма живёт то во всю ширину поля, то в
        // колонке 440 px, и раскладка полей должна следовать за шириной
        // панели, а не за шириной окна.
        '@container shrink-0 rounded-lg border border-line bg-panel ' +
        // Раскрытая форма встаёт колонкой справа, а не растягивается во всю
        // ширину поверх поля: диспетчер вводит задержку конкретной бригады и
        // должен видеть её маршрут, иначе от карты остаётся полоса, а от
        // списка две строки.
        // Высота ограничена так, чтобы форма не доросла до очереди решений
        // наверху: та перекрывалась панелью и переставала читаться.
        (open
          ? 'lg:absolute lg:bottom-3 lg:right-3 lg:z-30 lg:w-[440px] ' +
            'lg:max-h-[calc(100%-96px)] lg:overflow-auto ' +
            'lg:shadow-[0_8px_32px_rgb(10_14_20/0.22)]'
          : '')
      }
    >
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex h-10 w-full items-center gap-2 px-3 text-left"
      >
        <Lightning size={15} weight="fill" aria-hidden className="text-accent" />
        <span className="shrink-0 text-[13px] font-medium">Событие в течение дня</span>
        <span className="truncate text-[12px] text-ink-3">
          новая заявка или авария, отмена, задержка, бригада выбыла
        </span>
        <CaretDown
          size={12}
          weight="bold"
          aria-hidden
          className={'ml-auto text-ink-3 transition-transform ' + (open ? 'rotate-180' : '')}
        />
      </button>

      {open ? (
        <div className="flex flex-col gap-3 border-t border-line px-3 py-3">
          {/* Как только посчитан предпросмотр, поля уходят: разговор идёт уже
              о последствиях, а форма занимает место решения «применить или
              отказаться» и выталкивает его за край панели. */}
          {preview ? (
            <button
              type="button"
              onClick={() => replan.reset()}
              className="flex w-fit items-center gap-2 rounded-md border border-line
                         px-2 py-1 text-[12px] text-ink-2 transition-colors duration-[120ms]
                         hover:border-line-2 hover:bg-raised"
            >
              Изменить событие
            </button>
          ) : null}

          {preview ? null : (
            <KindPicker
              value={draft.kind}
              onChange={(kind) => change({ ...EMPTY_DRAFT, kind, at: draft.at })}
            />
          )}

          {preview ? null : (
          <div className="grid gap-3 @[400px]:grid-cols-2 @[760px]:grid-cols-4">
            <EventFields plan={plan} draft={draft} onChange={change} />
          </div>
          )}

          {preview ? null : (
          <div className="flex flex-wrap items-center gap-3">
            {/* Высота строки и размер флажка доведены до 24 px: цель меньше
                этого не берётся ни пальцем, ни мышью с первого раза. */}
            {draft.kind === 'urgent_order' && draft.work !== 'emergency' ? (
              // Обычная заявка встаёт только в свободное окно и план не
              // перестраивает: пересборка дня - право аварии (организаторы, 22.09).
              <span className="text-[12px] text-ink-3">
                Встанет только в свободное окно, чужие визиты не сдвинет
              </span>
            ) : (
              <label className="flex min-h-6 cursor-pointer items-center gap-2 text-[13px] text-ink-2">
                <input
                  type="checkbox"
                  className="size-4"
                  checked={draft.mode === 'full'}
                  onChange={(event) =>
                    change({ ...draft, mode: event.target.checked ? 'full' : 'minimal' })
                  }
                />
                Пересобрать остаток дня целиком
              </label>
            )}

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
          )}

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
                Предпросмотр. Рабочий день пока не изменился
              </span>
              <EventPreview
                before={plan}
                preview={preview}
                onSelect={onSelectOrder}
                minimal={draft.mode === 'minimal'}
              />
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
