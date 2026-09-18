import { describe, expect, it } from 'vitest';

import { plural } from './text';

describe('числительные', () => {
  it('согласует окончания', () => {
    expect(plural(1, 'заявка', 'заявки', 'заявок')).toBe('заявка');
    expect(plural(3, 'заявка', 'заявки', 'заявок')).toBe('заявки');
    expect(plural(11, 'заявка', 'заявки', 'заявок')).toBe('заявок');
    expect(plural(21, 'заявка', 'заявки', 'заявок')).toBe('заявка');
  });
});
