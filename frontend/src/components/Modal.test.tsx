import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

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
