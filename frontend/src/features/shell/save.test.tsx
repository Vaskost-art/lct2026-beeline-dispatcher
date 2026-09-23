import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { SaveSection } from './SaveSection';

function show(journal: boolean | undefined) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(new Response('{"ok":true,"data":{"exists":false}}')),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SaveSection open region="vostok" planned journal={journal} />
    </QueryClientProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe('сохранение дня', () => {
  it('без базы предупреждает, что день пропадёт при перезапуске', () => {
    show(false);
    expect(screen.getByText(/пропадёт при/)).toBeInTheDocument();
  });

  it('с базой не пугает зря', () => {
    show(true);
    expect(screen.queryByText(/пропадёт при/)).not.toBeInTheDocument();
  });
});
