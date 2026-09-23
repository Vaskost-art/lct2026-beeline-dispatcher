import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { PlanPayload } from '../../api/types';
import { IdleCrews } from './IdleCrews';

// Форма ответа сервиса: пустых маршрутов в `routes` нет, свободная бригада
// видна только по флагу `used` в списке бригад.
const plan = {
  routes: [{ engineer_id: 'Бригада 1', stops: [{ order_id: '1' }] }],
  engineers: [
    { id: 'Бригада 1', name: 'Бригада 1', vehicle: 'Автомобиль', used: true },
    { id: 'Бригада 5', name: 'Бригада 5', vehicle: 'Пешеход', used: false },
  ],
  unassigned: [{ order_id: '9' }],
} as unknown as PlanPayload;

describe('свободные бригады', () => {
  it('бригада без заявок видна, как бы сервис ни отдавал маршруты', () => {
    render(<IdleCrews plan={plan} onUnassigned={() => {}} />);
    expect(screen.getByText(/Бригада 5 \(без машины\)/)).toBeInTheDocument();
  });
});
