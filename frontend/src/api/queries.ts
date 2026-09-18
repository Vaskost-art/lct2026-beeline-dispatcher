/** Запросы к сервису.

Поздний ответ на устаревший ключ отбрасывается устройством библиотеки: в
прежней витрине эта гонка чинилась счётчиком поколений вручную.
*/
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { request, send } from './client';
import type {
  Meta,
  OrderExplanation,
  PlanPayload,
  ReplanPayload,
  ReplanRequest,
} from './types';

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

/** Объяснение назначения одной заявки.

Ключ включает номер заявки, поэтому поздний ответ на прежнюю заявку
отбрасывается устройством библиотеки: в прежней витрине эта гонка чинилась
счётчиком поколений вручную.
*/
export function useExplanation(region: string | null, orderId: string | null) {
  return useQuery({
    queryKey: ['explain', region ?? '', orderId ?? ''],
    enabled: Boolean(region && orderId),
    queryFn: () =>
      send<OrderExplanation>('/api/explain', { region, order_id: orderId }),
  });
}

/** Событие в течение дня.

Предпросмотр и применение это один и тот же запрос с разным полем `apply`:
сервис считает одно и то же, и предпросмотр не может разойтись с тем, что
получится на самом деле.
*/
export function useReplan() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: ReplanRequest) => send<ReplanPayload>('/api/replan', body),
    onSuccess: (answer) => {
      // Рабочий день меняется только при «применить». Предпросмотр живёт
      // в своём состоянии и в кеш плана не попадает.
      if (answer.applied) client.setQueryData(planKey(answer.region), answer);
    },
  });
}
