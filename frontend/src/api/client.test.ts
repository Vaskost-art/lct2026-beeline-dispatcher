import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError, request } from './client';

function answer(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

describe('обращение к сервису', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('разворачивает конверт удачного ответа', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(answer({ ok: true, data: { regions: [] } })));

    await expect(request('/api/meta')).resolves.toEqual({ regions: [] });
  });

  it('несёт код ошибки, а не только текст', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          answer({ ok: false, error: { code: 'plan_not_built', message: 'Сначала посчитайте' } }, 409),
        ),
    );

    await expect(request('/api/plan/vostok')).rejects.toMatchObject({
      code: 'plan_not_built',
      message: 'Сначала посчитайте',
    });
  });

  it('не выдаёт обрыв связи за ответ сервиса', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));

    await expect(request('/api/meta')).rejects.toBeInstanceOf(ApiError);
  });
});
