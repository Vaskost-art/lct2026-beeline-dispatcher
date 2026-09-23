import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { UploadDialog } from './UploadDialog';

afterEach(() => vi.restoreAllMocks());

describe('загрузка набора', () => {
  it('слишком большой файл отклоняется до отправки с понятной причиной', async () => {
    const fetcher = vi.fn();
    vi.stubGlobal('fetch', fetcher);
    const client = new QueryClient();
    const { baseElement } = render(
      <QueryClientProvider client={client}>
        <UploadDialog open onClose={() => {}} onLoaded={() => {}} />
      </QueryClientProvider>,
    );

    const big = new File(['x'], 'big.csv');
    Object.defineProperty(big, 'size', { value: 9 * 1024 * 1024 });
    const input = baseElement.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [big] } });

    expect(await screen.findByRole('alert')).toHaveTextContent('больше 8 МБ');
    expect(fetcher).not.toHaveBeenCalled();
  });
});
