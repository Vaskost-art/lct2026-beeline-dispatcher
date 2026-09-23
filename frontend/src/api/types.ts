/** Форма ответов сервиса.

Типы повторяют то, что собирает `api/payload.py`. Проверок схемы через Zod
нет сознательно: сервис свой и меняется вместе с экраном, а граница доверия
проходит по загрузке файлов заказчика и проверяется там.
*/
import type { RiskReport } from './reports';

export interface Order {
  id: string;
  lat: number;
  lon: number;
  address: string;
  district: string;
  duration_min: number;
  /** Время приходит строкой ЧЧ:ММ: экрану считать минуты незачем. */
  window_start: string;
  window_end: string;
  priority: string;
  required_skill: string;
  required_vehicle: string | null;
  equipment: string[];
  type_bk: string;
  type_hd: string;
  control_engineer: string | null;
  geocode_precision: string;
  assigned_to: string | null;
}

export interface Engineer {
  id: string;
  name: string;
  lat: number;
  lon: number;
  start_address: string;
  shift_start: string;
  shift_end: string;
  shift_text: string;
  work_end: string;
  break_min: number;
  skills: string[];
  vehicle: string;
  used: boolean;
}

export interface Stop {
  order_id: string;
  arrival: string;
  start: string;
  end: string;
  travel_min: number;
  travel_km: number;
  wait_min: number;
  /** Чем добирались: «12 мин пешком» или «25 мин: 12 пешком и 13 на транспорте». */
  travel_text?: string;
  /** То же коротко: «пешком и транспорт». */
  travel_mode?: string;
}

export interface Route {
  engineer_id: string;
  stops: Stop[];
  total_km: number;
  total_travel_min: number;
  total_work_min: number;
}

export interface Unassigned {
  order_id: string;
  reason: string;
  reason_text: string;
}

export interface Metrics {
  strategy: string;
  used_engineers: number;
  engineers_available: number;
  orders_total: number;
  orders_assigned: number;
  orders_unassigned: number;
  assigned_share: number;
  total_km: number;
  /** Пробег на автомобиле: бензин тратится только на него. */
  car_km: number;
  /** Пешком и городским транспортом. */
  no_car_km: number;
  total_travel_min: number;
  total_work_min: number;
  travel_share: number;
  avg_km_per_order: number;
  solver_status: string;
  solve_seconds: number;
}

/** Ход смены: сколько заявок закрыто, отменено и в работе. */
export interface DayProgress {
  done: number;
  cancelled: number;
  in_progress: number;
  sent: number;
}

export interface PickupRow {
  engineer_id: string;
  items: Record<string, number>;
  total: number;
  text: string;
}

export interface CrewProfile {
  vehicle: string;
  skills: string[];
  shift: string;
}

export interface Shortfall {
  missing: number;
  assigned: number;
  still_unassigned: number;
  /** Каких именно бригад не хватает: транспорт, навыки, часы смены. */
  profiles: CrewProfile[];
  reason: string;
  limited_by_people: boolean;
}

export interface GeoWarning {
  approx_count: number;
  total: number;
  share: number;
  level: string;
  order_ids: string[];
  text: string;
}

export interface RouteSummary {
  engineer_id: string;
  used: boolean;
  summary: string;
  steps: string[];
}

export interface PlanPayload {
  region: string;
  region_name: string;
  strategy: string;
  strategy_title: string;
  solver_status: string;
  solver_status_text: string;
  solve_seconds: number;
  locked: Record<string, string>;
  undo: string[];
  /** Решения человека за смену: ручные переносы, применённые события,
      восстановление сохранения. Пересчёты сюда не входят. */
  manual_changes: string[];
  metrics: Metrics;
  explanation: { lines: string[]; text: string };
  engineers: Engineer[];
  orders: Order[];
  routes: Route[];
  unassigned: Unassigned[];
  route_summaries: RouteSummary[];
  risk: RiskReport;
  pickup: PickupRow[];
  shortfall: Shortfall;
  geo: GeoWarning;
  /** Что с заявкой прямо сейчас: заявка -> статус. Пусто значит «Отправлено». */
  statuses: Record<string, string>;
  progress: DayProgress;
  /** Время смены: момент последнего применённого события, «ЧЧ:ММ» или пусто. */
  clock?: string;
}

export type * from './reports';
export type * from './replan';
export type * from './checks';
