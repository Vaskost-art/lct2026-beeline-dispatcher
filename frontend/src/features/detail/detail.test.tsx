import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { Order } from '../../api/types';
import { OrderDetail } from './OrderDetail';

function explanation(orderId: string) {
  return {
    order_id: orderId,
    assigned: true,
    headline: `Заявку ${orderId} выполняет «Бригада 1»`,
    facts: [['Адрес', 'Москва, улица, дом']] as [string, string][],
    alternatives: [],
  };
}

/** Ответ на первую заявку приходит позже, чем на вторую. */
function lateFirst() {
  let call = 0;
  return vi.fn().mockImplementation((_path: string, init?: RequestInit) => {
    const body = JSON.parse(String(init?.body)) as { order_id: string };
    call += 1;
    const delay = call === 1 ? 60 : 0;
    return new Promise<Response>((resolve) => {
      setTimeout(
        () => resolve(new Response(JSON.stringify({ ok: true, data: explanation(body.order_id) }))),
        delay,
      );
    });
  });
}

function show(orderId: string, order?: Order) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OrderDetail region="vostok" orderId={orderId} order={order} onClose={() => {}} />
    </QueryClientProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe('карточка заявки', () => {
  it('поздний ответ на прошлую заявку не подменяет открытую', async () => {
    vi.stubGlobal('fetch', lateFirst());

    const { rerender, container } = show('1');
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <OrderDetail region="vostok" orderId="2" order={undefined} onClose={() => {}} />
      </QueryClientProvider>,
    );

    await waitFor(() => expect(screen.getByText(/Заявку 2 выполняет/)).toBeInTheDocument());
    // Ответ на первую заявку приходит последним и не должен ничего подменить.
    await new Promise((done) => setTimeout(done, 120));
    expect(container.textContent).not.toContain('Заявку 1 выполняет');
    expect(screen.getByTestId('detail-order')).toHaveTextContent('2');
  });
});
