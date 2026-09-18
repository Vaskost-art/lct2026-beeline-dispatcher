import { ListBullets, MapTrifold } from '@phosphor-icons/react';
import { useState } from 'react';

import type { PlanPayload } from '../../api/types';
import type { Day } from '../../state/day';
import { OrderDetail } from '../detail/OrderDetail';
import { MapView } from '../map/MapView';
import { WorkList } from '../routes/WorkList';

interface Props {
  plan: PlanPayload;
  day: Day;
  apiKey: string;
}

/** Рабочее поле: список слева, карта справа.

На узком экране они не делят место пополам, а сменяют друг друга: половина
телефона под карту бесполезна обоим.
*/
export function Workspace({ plan, day, apiKey }: Props) {
  const [narrowView, setNarrowView] = useState<'list' | 'map'>('list');

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2">
      <div className="flex gap-1 rounded-md border border-line bg-panel p-1 lg:hidden">
        {(
          [
            ['list', 'Список', ListBullets],
            ['map', 'Карта', MapTrifold],
          ] as const
        ).map(([key, title, Icon]) => (
          <button
            key={key}
            type="button"
            aria-pressed={narrowView === key}
            onClick={() => setNarrowView(key)}
            className={
              'flex h-8 flex-1 items-center justify-center gap-2 rounded-sm text-[13px] font-medium ' +
              'transition-colors duration-[120ms] ' +
              (narrowView === key ? 'bg-raised text-ink' : 'text-ink-3 hover:text-ink')
            }
          >
            <Icon size={15} weight="bold" aria-hidden />
            {title}
          </button>
        ))}
      </div>

      <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[minmax(0,440px)_minmax(0,1fr)]">
        <div className={'min-h-0 min-w-0 ' + (narrowView === 'list' ? 'flex' : 'hidden lg:flex')}>
          <WorkList
            plan={plan}
            selected={day.selectedOrder}
            onSelect={(orderId) => {
              day.selectOrder(orderId);
            }}
          />
        </div>

        <div
          className={
            'relative min-h-0 min-w-0 ' + (narrowView === 'map' ? 'flex' : 'hidden lg:flex')
          }
        >
          <MapView
            plan={plan}
            hiddenCrews={day.hiddenCrews}
            selected={day.selectedOrder}
            apiKey={apiKey}
            theme={day.theme}
            onSelect={day.selectOrder}
          />
          {day.selectedOrder ? (
            <OrderDetail
              region={plan.region}
              orderId={day.selectedOrder}
              order={plan.orders.find((item) => item.id === day.selectedOrder)}
              onClose={() => day.selectOrder(null)}
            />
          ) : null}
        </div>
      </div>
    </div>
  );
}
