/** Запросы к сервису.

Поздний ответ на устаревший ключ отбрасывается устройством библиотеки: в
прежней витрине эта гонка чинилась счётчиком поколений вручную.
*/
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { request, send } from './client';
import type {
  ComparePayload,
  Meta,
  OrderExplanation,
  PlanPayload,
  ReplanPayload,
  ReplanRequest,
  SavedDayInfo,
  ValidationReport,
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

/** Сравнение способов расчёта. Считается по требованию: три плана подряд
    занимают время, и на главном экране это не нужно. */
export function useCompare(region: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ['compare', region ?? ''],
    enabled: Boolean(region) && enabled,
    queryFn: () => request<ComparePayload>(`/api/compare/${region ?? ''}`),
    staleTime: 5 * 60 * 1000,
  });
}

/** Независимая проверка плана на ограничения. */
export function useValidation(region: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ['validate', region ?? ''],
    enabled: Boolean(region) && enabled,
    queryFn: () => request<ValidationReport>(`/api/validate/${region ?? ''}`),
  });
}

/** Сохранённый рабочий день участка. */
export function useSavedDay(region: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ['saved', region ?? ''],
    enabled: Boolean(region) && enabled,
    queryFn: () => request<SavedDayInfo>(`/api/plan/saved/${region ?? ''}`),
  });
}

export function useSaveDay() {
  return useMutation({
    mutationFn: (body: { region: string; name: string }) =>
      send<{ saved: boolean; name: string; saved_at: string }>('/api/plan/save', body),
  });
}

export function useRestoreDay() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { region: string }) => send<PlanPayload>('/api/plan/restore', body),
    onSuccess: (plan) => client.setQueryData(planKey(plan.region), plan),
  });
}

/** Ручной перенос заявки другой бригаде.

Решение диспетчера переживает пересчёт: сервис закрепляет заявку за выбранной
бригадой, иначе следующий расчёт молча отменил бы то, что человек сделал.
*/
export function useReassign() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { region: string; order_id: string; engineer_id: string | null }) =>
      send<PlanPayload>('/api/reassign', body),
    onSuccess: (plan) => client.setQueryData(planKey(plan.region), plan),
  });
}

/** Отметка хода работ: диспетчер записывает то, что сообщила бригада.

Организаторы: факт выполнения или отмены фиксирует диспетчер, и закрытые
заявки в дальнейшее планирование не включаются. Поэтому отметка - не
украшение списка, а вход в перепланирование.
*/
export function useOrderStatus() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { region: string; order_id: string; status: string }) =>
      send<PlanPayload>('/api/order/status', body),
    onSuccess: (plan) => client.setQueryData(planKey(plan.region), plan),
  });
}

/** Передача оборудования между бригадами в течение дня.

Заказчик: оборудование выдаётся утром, но днём его можно передавать. Без
этого ограничение по сумке было бы тупиком: бригада рядом с заявкой, а
роутер у соседа через квартал.
*/
export function useEquipmentTransfer() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      region: string;
      source: string;
      target: string;
      item: string;
      count: number;
    }) => send<PlanPayload>('/api/equipment/transfer', body),
    onSuccess: (plan) => client.setQueryData(planKey(plan.region), plan),
  });
}

/** Шаг назад: вернуть план к состоянию до последнего изменения.

За смену диспетчер вносит десятки правок, и ошибиться в одной - обычное дело.
Без отката единственным способом исправиться было пересобрать день целиком,
то есть потерять и все остальные решения.
*/
export function useUndo() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { region: string }) => send<PlanPayload>('/api/undo', body),
    onSuccess: (plan) => client.setQueryData(planKey(plan.region), plan),
  });
}
