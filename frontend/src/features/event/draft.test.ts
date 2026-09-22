import { describe, expect, it } from 'vitest';

import type { PlanPayload } from '../../api/types';
import { EMPTY_DRAFT, WORK_MINUTES, toRequest } from './draft';

const plan = {
  region: 'vostok',
  orders: [{ id: '1', district: 'Таганский', lat: 55.74, lon: 37.65 }],
} as unknown as PlanPayload;

describe('новая заявка днём', () => {
  it('обычная заявка не просит пересобрать день, даже если флажок стоял', () => {
    const draft = { ...EMPTY_DRAFT, work: 'local' as const, district: 'Таганский', mode: 'full' as const };

    const request = toRequest(draft, plan, false);

    expect(request.mode).toBe('minimal');
    expect(request.new_order?.required_skill).toBe('Локальные работы');
    expect(request.new_order?.id.startsWith('НОВАЯ-')).toBe(true);
  });

  it('авария сохраняет выбранный режим и свой навык', () => {
    const draft = { ...EMPTY_DRAFT, district: 'Таганский', mode: 'full' as const };

    const request = toRequest(draft, plan, false);

    expect(request.mode).toBe('full');
    expect(request.new_order?.required_skill).toBe('Аварийные работы');
    expect(request.new_order?.id.startsWith('АВАРИЯ-')).toBe(true);
  });

  it('длительность по умолчанию берётся из норматива заказчика', () => {
    expect(EMPTY_DRAFT.durationMin).toBe(WORK_MINUTES.emergency);
    expect(WORK_MINUTES.local).toBeLessThan(WORK_MINUTES.emergency);
  });
});
