import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { Alternative } from '../../api/types';
import { Alternatives } from './Alternatives';

const items: Alternative[] = [
  { engineer_id: 'Бригада 2', possible: false, reason: 'нет навыка «Аварийные работы»' },
];

describe('кто ещё мог взять', () => {
  it('у назначенной заявки разбор свёрнут: нужно краткое обоснование', () => {
    const { container } = render(<Alternatives items={items} total={1} collapsed />);

    const details = container.querySelector('details');
    expect(details).not.toBeNull();
    expect(details?.open).toBe(false);
  });

  it('у нераспределённой заявки разбор раскрыт: он и есть ответ', () => {
    const { container } = render(<Alternatives items={items} total={1} />);

    expect(container.querySelector('details')).toBeNull();
    expect(screen.getByText('нет навыка «Аварийные работы»')).toBeVisible();
  });
});
