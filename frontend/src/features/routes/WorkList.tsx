import { MagnifyingGlass, X } from '@phosphor-icons/react';
import { useMemo, useState } from 'react';

import { Tabs } from '../../components/Tabs';
import type { PlanPayload } from '../../api/types';
import { UnassignedList } from '../unassigned/UnassignedList';
import { RouteRow } from './RouteRow';

interface Props {
  plan: PlanPayload;
  selected: string | null;
  focusCrew: string | null;
  onSelect: (orderId: string) => void;
  onFocusCrew: (crew: string | null) => void;
}

const COLUMNS = 'grid-cols-[14px_10px_minmax(0,1fr)_56px_64px_52px]';

/** Работа дня двумя вкладками: что разошлось и что осталось.

Поиск обязателен: заявок под сотню, и без него единственный способ найти
нужную это читать список глазами.
*/
export function WorkList({ plan, selected, focusCrew, onSelect, onFocusCrew }: Props) {
  const [tab, setTab] = useState('routes');
  const [query, setQuery] = useState('');
  const used = plan.routes.filter((route) => route.stops.length > 0);
  const needle = query.trim().toLowerCase();

  // Поиск идёт по номеру, адресу и району: заявку помнят по-разному, и
  // заставлять вспоминать именно номер незачем.
  const matched = useMemo(() => {
    if (!needle) return null;
    return new Set(
      plan.orders
        .filter(
          (order) =>
            order.id.toLowerCase().includes(needle) ||
            order.address.toLowerCase().includes(needle) ||
            order.district.toLowerCase().includes(needle),
        )
        .map((order) => order.id),
    );
  }, [needle, plan.orders]);

  const shown = matched
    ? used.filter((route) => route.stops.some((stop) => matched.has(stop.order_id)))
    : used;

  return (
    <section
      data-testid="work-list"
      className="flex min-h-0 w-full min-w-0 flex-col overflow-hidden rounded-lg border border-line bg-panel"
    >
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

      <div className="flex h-9 shrink-0 items-center gap-2 border-b border-line px-3">
        <MagnifyingGlass size={14} aria-hidden className="shrink-0 text-ink-4" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Номер заявки, адрес или район"
          aria-label="Поиск по заявкам"
          className="min-w-0 flex-1 bg-transparent text-[12px] outline-none placeholder:text-ink-4"
        />
        {query ? (
          <button
            type="button"
            onClick={() => setQuery('')}
            aria-label="Очистить поиск"
            className="rounded p-0.5 text-ink-4 hover:text-ink"
          >
            <X size={12} weight="bold" />
          </button>
        ) : null}
      </div>

      {tab === 'routes' ? (
        <div
          className={`grid h-7 shrink-0 ${COLUMNS} items-center gap-2 border-b border-line bg-raised/50 pl-2 pr-3`}
        >
          <span />
          <span />
          <span className="eyebrow">Бригада</span>
          <span className="eyebrow text-right">Заявок</span>
          <span className="eyebrow text-right">Км</span>
          <span className="eyebrow text-right">Груз</span>
        </div>
      ) : null}

      <div className="min-h-0 flex-1 overflow-auto overscroll-contain">
        {tab === 'routes' ? (
          shown.length === 0 ? (
            <p className="px-3 py-6 text-center text-[13px] text-ink-3">
              По запросу «{query}» ничего нет. Проверьте номер, адрес или район.
            </p>
          ) : (
            <ul>
              {shown.map((route) => (
                <RouteRow
                  key={route.engineer_id}
                  route={route}
                  index={plan.routes.indexOf(route)}
                  orders={plan.orders}
                  open={focusCrew === route.engineer_id}
                  focused={focusCrew === route.engineer_id}
                  selected={selected}
                  onToggle={() =>
                    onFocusCrew(focusCrew === route.engineer_id ? null : route.engineer_id)
                  }
                  onSelect={onSelect}
                />
              ))}
            </ul>
          )
        ) : (
          <UnassignedList
            items={
              matched
                ? plan.unassigned.filter((item) => matched.has(item.order_id))
                : plan.unassigned
            }
            orders={plan.orders}
            selected={selected}
            onSelect={onSelect}
          />
        )}
      </div>
    </section>
  );
}
