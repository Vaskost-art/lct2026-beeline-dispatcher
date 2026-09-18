import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import type { Order, Route } from '../../api/types';
import { UnassignedList } from '../unassigned/UnassignedList';
import { RouteRow } from './RouteRow';

const order: Order = {
  id: '74198', lat: 55.7, lon: 37.6, address: 'Улица, дом', district: 'Таганский',
  duration_min: 70, window_start: '10:00', window_end: '14:00', priority: 'Обычная',
  required_skill: 'Локальные работы', required_vehicle: null, equipment: ['Роутер'],
  type_bk: 'Подключение', type_hd: 'Конвергенция', control_engineer: null,
  geocode_precision: 'exact', assigned_to: 'Бригада 1',
};

const route: Route = {
  engineer_id: 'Бригада 1',
  stops: [{ order_id: '74198', arrival: '10:05', start: '10:05', end: '11:15', travel_min: 12, travel_km: 3.4, wait_min: 0 }],
  total_km: 3.4, total_travel_min: 12, total_work_min: 70,
};

describe('список маршрутов', () => {
  it('раскрывается в остановки с оборудованием', async () => {
    render(<RouteRow route={route} orders={[order]} onSelect={() => {}} selected={null} />);

    await userEvent.click(screen.getByRole('button', { name: /Бригада 1/ }));

    expect(screen.getByText(/Роутер/)).toBeInTheDocument();
    expect(screen.getByText(/Улица, дом/)).toBeInTheDocument();
  });

  it('обычный приоритет пишет словом, а не прочерком', async () => {
    render(<RouteRow route={route} orders={[order]} onSelect={() => {}} selected={null} />);

    await userEvent.click(screen.getByRole('button', { name: /Бригада 1/ }));

    expect(screen.getByText('обычная')).toBeInTheDocument();
    expect(screen.queryByText('—')).not.toBeInTheDocument();
  });
});

describe('нераспределённые', () => {
  it('называют причину словами, а не кодом', () => {
    render(
      <UnassignedList
        items={[{ order_id: '53587', reason: 'vehicle_required', reason_text: 'Требуется автомобиль, а у свободных бригад его нет' }]}
        orders={[{ ...order, id: '53587', assigned_to: null }]}
        onSelect={() => {}}
        selected={null}
      />,
    );

    expect(screen.getByText(/Требуется автомобиль/)).toBeInTheDocument();
    expect(screen.queryByText('vehicle_required')).not.toBeInTheDocument();
  });
});
