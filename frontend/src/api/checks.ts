/** Проверки плана, сравнение способов расчёта и сохранение дня. */
import type { Metrics } from './types';

export interface CompareRow {
  key: string;
  title: string;
  /** Чем посчитано: решатель или правило. Стоит подписью, не в заголовке. */
  method: string;
  hint: string;
  metrics: Metrics;
}

export interface ComparePayload {
  region: string;
  region_name: string;
  rows: CompareRow[];
  vs_baseline: {
    orders_assigned_delta: number;
    used_engineers_delta: number;
    total_km_delta: number;
    km_per_order_pct: number | null;
  };
  basis: string;
  /** День на экране отличается от дня, по которому считалось сравнение:
      к нему уже применены события. Тогда числа в строке «наш план» и в
      сводке расходятся, и об этом надо сказать прямо. */
  changed: boolean;
}

export interface ValidationRule {
  key: string;
  title: string;
  checked: number;
  failed: number;
}

export interface Violation {
  rule: string;
  text: string;
  engineer_id?: string;
  order_id?: string;
}

export interface ValidationReport {
  ok: boolean;
  checked_routes: number;
  checked_stops: number;
  violations: Violation[];
  by_rule: Record<string, number>;
  /** Перечень правил со счётчиками: без него зелёный ответ ничего не
      доказывает - не видно, что именно проверялось. */
  rules: ValidationRule[];
  orders_total: number;
  /** Заявки, которых в плане нет. Правила их не проверяют, но молчать о них
      нельзя: иначе «нарушений нет» читается как «день в порядке». */
  not_in_plan: number;
}

export interface SavedDayInfo {
  exists: boolean;
  name?: string;
  saved_at?: string;
}
