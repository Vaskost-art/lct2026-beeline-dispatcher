import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { App } from './App';

describe('каркас', () => {
  it('показывает название сервиса', () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"ok":true,"data":{}}')));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <App />
      </QueryClientProvider>,
    );

    expect(screen.getByText(/Планировщик выездных работ/)).toBeInTheDocument();
  });
});
