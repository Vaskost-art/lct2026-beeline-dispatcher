import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { Metric } from './Metric';
import { Modal } from './Modal';

describe('модальное окно', () => {
  it('закрывается по Escape', async () => {
    const onClose = vi.fn();
    render(
      <Modal open title="Сравнение" onClose={onClose}>
        тело
      </Modal>,
    );

    await userEvent.keyboard('{Escape}');

    expect(onClose).toHaveBeenCalled();
  });

  it('называет себя заголовком, а не просто рисует рамку', () => {
    render(
      <Modal open title="Сравнение" onClose={() => {}}>
        тело
      </Modal>,
    );

    expect(screen.getByRole('dialog', { name: 'Сравнение' })).toBeInTheDocument();
  });
});

describe('метрика', () => {
  it('во время пересчёта показывает прежнее значение, а не пустоту', () => {
    render(<Metric id="assigned" title="Назначено" value="61/66" stale />);

    const metric = screen.getByTestId('metric-assigned');
    expect(metric).toHaveTextContent('61/66');
    expect(metric.dataset.stale).toBe('true');
  });
});
