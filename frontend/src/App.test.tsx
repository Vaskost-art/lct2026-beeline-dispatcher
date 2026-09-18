import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { App } from './App';

describe('каркас', () => {
  it('показывает название сервиса', () => {
    render(<App />);
    expect(screen.getByText(/Планировщик выездных работ/)).toBeInTheDocument();
  });
});
