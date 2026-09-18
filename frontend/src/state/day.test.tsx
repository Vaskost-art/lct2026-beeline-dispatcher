import { act, renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { DayProvider, useDay } from './day';

const wrap = ({ children }: { children: ReactNode }) => <DayProvider>{children}</DayProvider>;

describe('состояние дня', () => {
  it('смена участка снимает выбор заявки', () => {
    const { result } = renderHook(() => useDay(), { wrapper: wrap });

    act(() => result.current.selectOrder('74198'));
    act(() => result.current.selectRegion('yugo_vostok'));

    // Заявка чужого участка на экране это ложь о плане.
    expect(result.current.selectedOrder).toBeNull();
  });

  it('помнит скрытые бригады по одной', () => {
    const { result } = renderHook(() => useDay(), { wrapper: wrap });

    act(() => result.current.toggleCrew('Бригада 1'));
    act(() => result.current.toggleCrew('Бригада 2'));
    act(() => result.current.toggleCrew('Бригада 1'));

    expect([...result.current.hiddenCrews]).toEqual(['Бригада 2']);
  });

  it('закрывает панель, не трогая выбранную заявку', () => {
    const { result } = renderHook(() => useDay(), { wrapper: wrap });

    act(() => result.current.selectOrder('74198'));
    act(() => result.current.openPanel('compare'));
    act(() => result.current.closePanel());

    expect(result.current.panel).toBeNull();
    expect(result.current.selectedOrder).toBe('74198');
  });
});
