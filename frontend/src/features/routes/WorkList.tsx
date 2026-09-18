import { useState } from 'react';

import { Tabs } from '../../components/Tabs';
import type { PlanPayload } from '../../api/types';
import { UnassignedList } from '../unassigned/UnassignedList';
import { RouteRow } from './RouteRow';

interface Props {
  plan: PlanPayload;
  selected: string | null;
  onSelect: (orderId: string) => void;
}

/** Работа дня двумя вкладками: что разошлось и что осталось. */
export function WorkList({ plan, selected, onSelect }: Props) {
  const [tab, setTab] = useState('routes');
  const used = plan.routes.filter((route) => route.stops.length > 0);

  return (
    <section className="flex min-h-0 w-full min-w-0 flex-col overflow-hidden rounded-lg border border-line bg-panel">
      <Tabs
        value={tab}
        onChange={setTab}
        items={[
          { key: 'routes', title: 'Маршруты', count: used.length },
          {
            key: 'unassigned',
            title: 'Без исполнителя',
            count: plan.unassigned.length,
            tone: 'alert',
          },
        ]}
      />

      <div className="min-h-0 flex-1 overflow-auto overscroll-contain">
        {tab === 'routes' ? (
          <ul>
            {used.map((route) => (
              <RouteRow
                key={route.engineer_id}
                route={route}
                index={plan.routes.indexOf(route)}
                orders={plan.orders}
                selected={selected}
                onSelect={onSelect}
              />
            ))}
          </ul>
        ) : (
          <UnassignedList
            items={plan.unassigned}
            orders={plan.orders}
            selected={selected}
            onSelect={onSelect}
          />
        )}
      </div>
    </section>
  );
}
