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

  it('вторая авария в ту же минуту получает свой номер', () => {
    const draft = { ...EMPTY_DRAFT, district: 'Таганский', at: '13:00' };
    const first = toRequest(draft, plan, false).new_order?.id ?? '';
    const withFirst = {
      ...plan,
      orders: [...plan.orders, { ...plan.orders[0], id: first }],
    } as PlanPayload;

    expect(toRequest(draft, withFirst, false).new_order?.id).not.toBe(first);
  });

  it('длительность по умолчанию берётся из норматива заказчика', () => {
    expect(EMPTY_DRAFT.durationMin).toBe(WORK_MINUTES.emergency);
    expect(WORK_MINUTES.local).toBeLessThan(WORK_MINUTES.emergency);
  });
});

describe('окно новой заявки', () => {
  it('авария начинается с момента поступления, окно ей не задают', () => {
    const draft = { ...EMPTY_DRAFT, district: 'Таганский', at: '13:10', windowStart: '16:00' };

    const request = toRequest(draft, plan, false);

    expect(request.new_order?.window_start).toBe('13:10');
    expect(request.new_order?.window_end).toBe('23:59');
  });

  it('у обычной заявки окно то, что задал диспетчер', () => {
    const draft = {
      ...EMPTY_DRAFT,
      work: 'connect' as const,
      district: 'Таганский',
      windowStart: '16:00',
      windowEnd: '18:00',
    };

    const request = toRequest(draft, plan, false);

    expect(request.new_order?.window_start).toBe('16:00');
    expect(request.new_order?.window_end).toBe('18:00');
  });
});
