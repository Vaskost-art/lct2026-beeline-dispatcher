import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { ComparePayload } from '../../api/types';
import { CompareDialog } from './CompareDialog';

function row(key: string, title: string, assigned: number, km: number) {
  return {
    key,
    title,
    hint: '',
    metrics: {
      orders_assigned: assigned,
      orders_total: 66,
      used_engineers: 8,
      total_km: km,
      avg_km_per_order: km / assigned,
    },
  };
}

const data = {
  region: 'vostok',
  region_name: 'Восток',
  rows: [
    row('baseline', 'Без оптимизации (базовый вариант по ТЗ)', 25, 141.9),
    row('greedy', 'Быстрый расчёт', 61, 204.7),
    row('optimized', 'Оптимальный план', 63, 142.0),
  ],
  basis: 'Сравнение посчитано по тому же дню, что показан на экране.',
} as unknown as ComparePayload;

function show() {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true, data }))),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <CompareDialog region="vostok" open onClose={() => {}} />
    </QueryClientProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe('сравнение вариантов', () => {
  it('показывает базовый вариант из ТЗ первой строкой', async () => {
    show();

    await waitFor(() => expect(screen.getAllByRole('row').length).toBeGreaterThan(1));
    const rows = screen.getAllByRole('row');
    expect(rows[1]?.textContent).toContain('базовый вариант по ТЗ');
  });

  it('не показывает распределение диспетчера', async () => {
    // Заказчик назвал его ориентиром, а не эталоном качества.
    show();

    await waitFor(() => expect(screen.getByText(/Задача нетривиальна/)).toBeInTheDocument());
    expect(screen.queryByText(/диспетчера/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/факт/i)).not.toBeInTheDocument();
  });
});
