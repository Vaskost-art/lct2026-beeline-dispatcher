/** События дня: предпросмотр и применение. */
import type { PlanPayload } from './types';

export interface PlanChange {
  order_id: string;
  status: string;
  from_engineer: string | null;
  to_engineer: string | null;
  from_position: number | null;
  to_position: number | null;
  /** На сколько минут сдвинулся визит: по нему предупреждают клиента. */
  shift_min?: number | null;
}

export interface ReplanDiff {
  event: { kind: string; title: string; at: string; description: string };
  changes: PlanChange[];
  /** Что стало с заявкой, поступившей днём. */
  new_order?: {
    order_id: string;
    priority: string;
    engineer_id: string | null;
    reason: string | null;
  };
  /** Через сколько бригада приедет на аварию. Ориентир организаторов - 1-2 часа. */
  reaction?: { engineer_id: string; minutes: number; target_min: number; within: boolean };
  /** Заявки, которые были в плане, а полная пересборка их сняла. */
  lost?: string[];
}

/** Ответ на событие: тот же план плюс что именно изменилось. */
export interface ReplanPayload extends PlanPayload {
  diff: ReplanDiff;
  narrative: string[];
  applied: boolean;
  frozen: Record<string, string[]>;
}

export interface NewOrderDraft {
  id: string;
  lat: number;
  lon: number;
  address: string;
  district: string;
  duration_min: number;
  window_start: string;
  window_end: string;
  required_skill: string;
  required_vehicle: string | null;
}

export interface ReplanRequest {
  region: string;
  kind: 'urgent_order' | 'cancel_order' | 'engineer_unavailable' | 'engineer_delayed';
  at: string;
  order_id?: string | null;
  engineer_id?: string | null;
  delay_min?: number;
  new_order?: NewOrderDraft | null;
  mode: 'minimal' | 'full';
  apply: boolean;
}
