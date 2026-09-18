import { describe, expect, it } from 'vitest';

import type { PlanPayload } from '../../api/types';
import { buildMapModel, crewColor } from './model';

const plan = {
  orders: [
    { id: '1', lat: 55.7, lon: 37.6, address: 'Улица, 1', district: 'Таганский', equipment: [] },
    { id: '2', lat: 55.8, lon: 37.7, address: 'Улица, 2', district: 'Выхино', equipment: [] },
  ],
  engineers: [
    { id: 'Бригада 1', name: 'Бригада 1', lat: 55.75, lon: 37.65, shift_text: '09:00–18:00', vehicle: 'Автомобиль' },
    { id: 'Бригада 2', name: 'Бригада 2', lat: 55.76, lon: 37.66, shift_text: '09:00–18:00', vehicle: 'Автомобиль' },
  ],
  routes: [
    { engineer_id: 'Бригада 1', stops: [{ order_id: '1', start: '10:00', end: '11:00' }] },
    { engineer_id: 'Бригада 2', stops: [{ order_id: '2', start: '10:00', end: '11:00' }] },
  ],
  unassigned: [{ order_id: '2', reason: 'window', reason_text: 'Окно уже закрыто' }],
} as unknown as PlanPayload;

describe('модель карты', () => {
  it('прячет скрытые бригады', () => {
    const model = buildMapModel(plan, new Set(['Бригада 1']));

    expect(model.routes.map((route) => route.id)).toEqual(['Бригада 2']);
  });

  it('оставляет бригаде её цвет, даже если соседнюю скрыли', () => {
    const full = buildMapModel(plan, new Set());
    const partial = buildMapModel(plan, new Set(['Бригада 1']));

    expect(partial.routes[0]?.color).toBe(full.routes[1]?.color);
    expect(crewColor(0)).not.toBe(crewColor(1));
  });

  it('нераспределённые заявки несут причину в подписи', () => {
    const model = buildMapModel(plan, new Set());

    expect(model.loose[0]?.title).toContain('не назначена');
    expect(model.loose[0]?.title).toContain('Окно уже закрыто');
  });
});
