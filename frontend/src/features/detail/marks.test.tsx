import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ReassignBox } from './ReassignBox';
import { StatusMarks } from './StatusMarks';

function wrap(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

afterEach(() => vi.restoreAllMocks());

describe('ход работ', () => {
  it('закрывающая отметка уходит только после подтверждения', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('{"ok":true,"data":{}}'));
    vi.stubGlobal('fetch', fetcher);
    wrap(<StatusMarks region="vostok" orderId="7" status="Отправлено" />);

    fireEvent.click(screen.getByRole('button', { name: 'Отменена' }));
    await new Promise((done) => setTimeout(done, 30));
    expect(fetcher).not.toHaveBeenCalled();
    expect(screen.getByText(/снимется с маршрута/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Отметить' }));
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
  });

  it('рабочая отметка ставится сразу', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('{"ok":true,"data":{}}'));
    vi.stubGlobal('fetch', fetcher);
    wrap(<StatusMarks region="vostok" orderId="7" status="Отправлено" />);

    fireEvent.click(screen.getByRole('button', { name: 'В пути' }));
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
  });
});

describe('передача заявки', () => {
  const crews = [
    { id: 'E1', name: 'Бригада 1' },
    { id: 'E2', name: 'Бригада 2' },
    { id: 'E3', name: 'Бригада 3' },
  ];

  it('у заявки без исполнителя действие называется «назначить»', () => {
    wrap(
      <ReassignBox region="vostok" orderId="7" holder={undefined} crews={crews} alternatives={[]} />,
    );
    expect(screen.getByText('Назначить бригаде')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Назначить' })).toBeInTheDocument();
  });

  it('подходящие бригады идут первыми, неподходящие помечены', () => {
    wrap(
      <ReassignBox
        region="vostok"
        orderId="7"
        holder="E1"
        crews={crews}
        alternatives={[
          { engineer_id: 'E2', possible: false, reason: 'нет навыка' },
          { engineer_id: 'E3', possible: true, reason: '', extra_km: 2.5 },
        ]}
      />,
    );
    const names = screen.getAllByRole('option').map((option) => option.textContent);
    expect(names).toEqual(['Выберите бригаду', 'Бригада 3, +2,5 км', 'Бригада 2, не подходит']);
  });
});
