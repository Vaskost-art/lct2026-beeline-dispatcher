/** Отчёты по плану: риск, справочники, объяснение заявки. */
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
  /** Ложатся ли версии дня в базу. Нет - день живёт до перезапуска сервиса. */
  journal: boolean;
}

export interface Alternative {
  engineer_id: string;
  possible: boolean;
  reason: string;
  extra_km?: number;
  vs_current_km?: number;
  blocked_by?: string | null;
}

export interface OrderExplanation {
  order_id: string;
  assigned: boolean;
  headline: string;
  engineer_id?: string;
  position?: number;
  /** Пары «название величины, значение»: готовый текст для человека. */
  facts: [string, string][];
  route_reason?: string;
  timing_reason?: string;
  reason?: string;
  alternatives: Alternative[];
  alternatives_total?: number;
  summary?: string;
}
