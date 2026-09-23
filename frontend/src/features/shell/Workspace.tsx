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

Две колонки включаются с 768: на планшете и в половине экрана ноутбука
карта - это и есть продукт, а список без неё выглядит выгрузкой из базы.
Сменяют друг друга они только на телефоне, где половина ширины бесполезна
обоим.
*/
export function Workspace({ plan, day, apiKey }: Props) {
  const [narrowView, setNarrowView] = useState<'list' | 'map'>('list');

  return (
    <div className="relative flex min-h-[520px] flex-1 flex-col gap-2 lg:min-h-0">
      <div className="flex gap-1 rounded-md border border-line bg-panel p-1 md:hidden">
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

      <div className="grid min-h-0 flex-1 gap-3 md:grid-cols-[minmax(0,300px)_minmax(0,1fr)]
                      lg:grid-cols-[minmax(0,440px)_minmax(0,1fr)]">
        <div className={'min-h-0 min-w-0 ' + (narrowView === 'list' ? 'flex' : 'hidden md:flex')}>
          <WorkList
            plan={plan}
            selected={day.selectedOrder}
            focusCrew={day.focusCrew}
            onSelect={day.selectOrder}
            onFocusCrew={day.focusOnCrew}
            onShortfall={() => day.openPanel('shortfall')}
            tab={day.listTab}
            onTab={day.showTab}
          />
        </div>

        <div
          className={
            'relative min-h-0 min-w-0 ' + (narrowView === 'map' ? 'flex' : 'hidden md:flex')
          }
        >
          <MapView
            plan={plan}
            hiddenCrews={day.hiddenCrews}
            focusCrew={day.focusCrew}
            selected={day.selectedOrder}
            apiKey={apiKey}
            theme={day.theme}
            onSelect={day.selectOrder}
            onToggleCrew={day.toggleCrew}
          />
        </div>
      </div>

      {/* Карточка живёт снаружи колонок: на телефоне колонка карты скрыта,
          и внутри неё объяснение оставалось бы невидимым. */}
      {day.selectedOrder ? (
        <OrderDetail
          key={day.selectedOrder}
          region={plan.region}
          orderId={day.selectedOrder}
          order={plan.orders.find((item) => item.id === day.selectedOrder)}
          status={plan.statuses?.[day.selectedOrder] ?? 'Отправлено'}
          crews={plan.engineers.map((engineer) => ({ id: engineer.id, name: engineer.name }))}
          onClose={() => day.selectOrder(null)}
        />
      ) : null}
    </div>
  );
}
