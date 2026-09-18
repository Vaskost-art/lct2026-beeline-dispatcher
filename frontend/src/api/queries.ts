/** Запросы к сервису.

Поздний ответ на устаревший ключ отбрасывается устройством библиотеки: в
прежней витрине эта гонка чинилась счётчиком поколений вручную.
*/
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { request, send } from './client';
import type { Meta, PlanPayload } from './types';

export const planKey = (region: string) => ['plan', region] as const;

export function useMeta() {
  return useQuery({ queryKey: ['meta'], queryFn: () => request<Meta>('/api/meta') });
}

/** Текущий план участка. Пока он не посчитан, сервис отвечает кодом. */
export function usePlan(region: string | null) {
  return useQuery({
    queryKey: planKey(region ?? ''),
    enabled: Boolean(region),
    queryFn: () => request<PlanPayload>(`/api/plan/${region ?? ''}`),
    // «План ещё не построен» это приглашение нажать кнопку, а не сбой,
    // повторять такой запрос бессмысленно.
    retry: false,
  });
}

export interface PlanRequest {
  region: string;
  strategy: string;
  time_limit_sec?: number;
}

export function useRunPlan() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: PlanRequest) => send<PlanPayload>('/api/plan', body),
    onSuccess: (plan) => {
      client.setQueryData(planKey(plan.region), plan);
    },
  });
}
