import type { PlanPayload } from '../../api/types';
import { type EventDraft, type NewOrderWork, WORK_MINUTES, WORK_TITLES } from './draft';

interface Props {
  plan: PlanPayload;
  draft: EventDraft;
  onChange: (next: EventDraft) => void;
}

const INPUT =
  'h-8 w-full min-w-0 rounded-md border border-line bg-panel px-2 text-[13px] text-ink ' +
  'hover:border-line-2';

function Label({ text, children }: { text: string; children: React.ReactNode }) {
  return (
    <label className="flex min-w-0 flex-col gap-1">
      <span className="text-[11px] font-medium uppercase tracking-[0.04em] text-ink-3">{text}</span>
      {children}
    </label>
  );
}

/** Поля события: своя пара на каждый вид, ничего лишнего на экране. */
export function EventFields({ plan, draft, onChange }: Props) {
  const crews = plan.engineers.filter((engineer) => engineer.used);
  const assigned = plan.orders.filter((order) => order.assigned_to);

  return (
    <>
      <Label text="Время события">
        <input
          type="time"
          className={`${INPUT} w-32 tnum`}
          value={draft.at}
          onChange={(event) => onChange({ ...draft, at: event.target.value })}
        />
      </Label>

      {draft.kind === 'cancel_order' ? (
        <Label text="Какая заявка отменилась">
          <select
            className={INPUT}
            value={draft.orderId}
            onChange={(event) => onChange({ ...draft, orderId: event.target.value })}
          >
            <option value="">выберите заявку</option>
            {assigned.map((order) => (
              <option key={order.id} value={order.id}>
                № {order.id} · {order.district} · {order.window_start}
              </option>
            ))}
          </select>
        </Label>
      ) : null}

      {draft.kind === 'engineer_unavailable' || draft.kind === 'engineer_delayed' ? (
        <Label text="Какая бригада">
          <select
            className={INPUT}
            value={draft.engineerId}
            onChange={(event) => onChange({ ...draft, engineerId: event.target.value })}
          >
            <option value="">выберите бригаду</option>
            {crews.map((engineer) => (
              <option key={engineer.id} value={engineer.id}>
                {engineer.name}
              </option>
            ))}
          </select>
        </Label>
      ) : null}

      {draft.kind === 'engineer_delayed' ? (
        <Label text="Задержка, мин">
          <input
            type="number"
            min={5}
            max={480}
            step={5}
            className={`${INPUT} w-24 tnum`}
            value={draft.delayMin}
            onChange={(event) => onChange({ ...draft, delayMin: Number(event.target.value) })}
          />
        </Label>
      ) : null}

      {draft.kind === 'urgent_order' ? (
        <>
          <Label text="Что пришло">
            <select
              className={INPUT}
              value={draft.work}
              onChange={(event) => {
                const work = event.target.value as NewOrderWork;
                // Длительность подставляется по нормативу заказчика: у аварии
                // и ремонта она различается почти втрое.
                onChange({ ...draft, work, durationMin: WORK_MINUTES[work] });
              }}
            >
              {WORK_TITLES.map(([key, title]) => (
                <option key={key} value={key}>
                  {title}
                </option>
              ))}
            </select>
          </Label>

          <Label text="Район">
            <select
              className={INPUT}
              value={draft.district}
              onChange={(event) => onChange({ ...draft, district: event.target.value })}
            >
              <option value="">выберите район</option>
              {[...new Set(plan.orders.map((order) => order.district))].sort().map((district) => (
                <option key={district} value={district}>
                  {district}
                </option>
              ))}
            </select>
          </Label>

          {draft.work === 'emergency' ? (
            <p className="self-end pb-1.5 text-[12px] text-ink-3">
              Окно: с момента поступления, бригада нужна за два часа. Точка
              ставится в центр района, время приезда в предпросмотре оценочное.
            </p>
          ) : (
            <>
          <Label text="Окно с">
            <input
              type="time"
              className={`${INPUT} w-32 tnum`}
              value={draft.windowStart}
              onChange={(event) => onChange({ ...draft, windowStart: event.target.value })}
            />
          </Label>

          <Label text="Окно до">
            <input
              type="time"
              className={`${INPUT} w-32 tnum`}
              value={draft.windowEnd}
              onChange={(event) => onChange({ ...draft, windowEnd: event.target.value })}
            />
          </Label>

            </>
          )}

          <Label text="Работы, мин">
            <input
              type="number"
              min={10}
              max={480}
              step={10}
              className={`${INPUT} tnum`}
              value={draft.durationMin}
              onChange={(event) => onChange({ ...draft, durationMin: Number(event.target.value) })}
            />
          </Label>
        </>
      ) : null}
    </>
  );
}
