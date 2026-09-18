/** Форма ответов сервиса.

Типы повторяют то, что собирает `api/payload.py`. Проверок схемы через Zod
нет сознательно: сервис свой и меняется вместе с экраном, а граница доверия
проходит по загрузке файлов заказчика и проверяется там.
*/

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
  total_travel_min: number;
  total_work_min: number;
  travel_share: number;
  avg_km_per_order: number;
  solver_status: string;
  solve_seconds: number;
}

export interface PickupRow {
  engineer_id: string;
  items: Record<string, number>;
  total: number;
  text: string;
}

export interface Shortfall {
  missing: number;
  assigned: number;
  still_unassigned: number;
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
}

export interface RiskRoute {
  engineer_id: string;
  used: boolean;
  tolerance_min: number;
  start_tolerance_min: number;
  risk: string;
  weakest_order_id: string | null;
  breaks_order_id: string | null;
  text: string;
}

export interface RiskReport {
  routes: RiskRoute[];
  by_risk: Record<string, number>;
  summary: string;
}

export interface RegionSummary {
  region_key: string;
  region_name: string;
  orders: number;
  engineers: number;
  urgent: number;
  builtin: boolean;
  dataset_events: unknown[];
}

export interface Meta {
  regions: RegionSummary[];
  skills: string[];
  vehicles: string[];
  priorities: string[];
  strategies: { key: string; title: string; full_title: string; hint: string }[];
  replan_kinds: { key: string; title: string }[];
  replan_modes: { key: string; title: string; hint: string }[];
  assumptions: { title: string; text: string }[];
  map_api_key: string;
}
