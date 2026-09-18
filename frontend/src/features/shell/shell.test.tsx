import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { DayProvider } from '../../state/day';
import { Screen } from './Screen';

function answer(data: unknown): Response {
  return new Response(JSON.stringify({ ok: true, data }), { status: 200 });
}

const META = {
  regions: [{ region_key: 'vostok', region_name: 'Восток', orders: 66, engineers: 8, urgent: 3, builtin: true, dataset_events: [] }],
  skills: [], vehicles: [], priorities: [], strategies: [], replan_kinds: [],
  replan_modes: [], assumptions: [], map_api_key: '',
};

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <DayProvider>
        <Screen />
      </DayProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe('первый вход', () => {
  it('ждёт выбора участка, сам ничего не считает и предлагает выбор', async () => {
    const fetcher = vi.fn().mockResolvedValue(answer(META));
    vi.stubGlobal('fetch', fetcher);

    show();
    expect(await screen.findByText(/Возьмите участок из выгрузки/)).toBeInTheDocument();

    const asked = fetcher.mock.calls.map((call) => String(call[0]));
    expect(asked.some((path) => path.includes('/api/plan'))).toBe(false);
    // Пустой экран даёт действие: участки кнопками прямо здесь.
    expect(await screen.findByRole('button', { name: /Восток/ })).toBeInTheDocument();
  });
});
