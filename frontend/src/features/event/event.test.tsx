import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { PlanPayload, ReplanPayload } from '../../api/types';
import { EventBar } from './EventBar';

const plan = {
  region: 'vostok',
  metrics: { orders_assigned: 61, orders_total: 66, total_km: 204.7, used_engineers: 8 },
  engineers: [{ id: 'Бригада 1', name: 'Бригада 1', used: true }],
  orders: [{ id: '74198', district: 'Таганский', window_start: '10:00', assigned_to: 'Бригада 1' }],
} as unknown as PlanPayload;

const answer = {
  ...plan,
  applied: false,
  metrics: { orders_assigned: 60, orders_total: 66, total_km: 210.1, used_engineers: 8 },
  diff: {
    event: { kind: 'engineer_delayed', title: 'Бригада задерживается', at: '13:00', description: 'Бригада задержится на 60 мин' },
    changes: [{ order_id: '74198', status: 'dropped', from_engineer: 'Бригада 1', to_engineer: null, from_position: 1, to_position: null }],
  },
  narrative: [],
  frozen: {},
} as unknown as ReplanPayload;

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <EventBar plan={plan} />
    </QueryClientProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe('событие дня', () => {
  it('предпросмотр показывает, что станет, и не меняет рабочий день', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ ok: true, data: answer })));
    vi.stubGlobal('fetch', fetcher);
    const user = userEvent.setup();

    show();
    await user.click(screen.getByRole('button', { name: /Событие в течение дня/ }));
    await user.click(screen.getByRole('button', { name: 'Задержка бригады' }));
    await user.selectOptions(screen.getByRole('combobox', { name: /Какая бригада/ }), 'Бригада 1');
    await user.click(screen.getByRole('button', { name: /Посмотреть, что изменится/ }));

    await waitFor(() => expect(screen.getByTestId('event-preview')).toBeInTheDocument());

    // Запрос ушёл с apply: false — рабочий день не тронут.
    const sent = JSON.parse(String(fetcher.mock.calls[0]?.[1]?.body)) as { apply: boolean };
    expect(sent.apply).toBe(false);
    expect(screen.getByText(/Рабочий день пока не изменился/)).toBeInTheDocument();
    // Видно и прежнее значение, и то, каким оно станет.
    expect(screen.getByTestId('event-preview').textContent).toContain('61');
    expect(screen.getByTestId('event-preview').textContent).toContain('60');
  });

  it('применение отправляет то же событие с пометкой «применить»', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ ok: true, data: answer })));
    vi.stubGlobal('fetch', fetcher);
    const user = userEvent.setup();

    show();
    await user.click(screen.getByRole('button', { name: /Событие в течение дня/ }));
    await user.click(screen.getByRole('button', { name: 'Задержка бригады' }));
    await user.selectOptions(screen.getByRole('combobox', { name: /Какая бригада/ }), 'Бригада 1');
    await user.click(screen.getByRole('button', { name: /Посмотреть, что изменится/ }));
    await waitFor(() => expect(screen.getByTestId('event-preview')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /Применить к дню/ }));

    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
    const applied = JSON.parse(String(fetcher.mock.calls[1]?.[1]?.body)) as {
      apply: boolean;
      kind: string;
      engineer_id: string;
    };
    expect(applied).toMatchObject({ apply: true, kind: 'engineer_delayed', engineer_id: 'Бригада 1' });
  });
});
