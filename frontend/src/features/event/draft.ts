import type { PlanPayload, ReplanRequest } from '../../api/types';

export type EventKind = ReplanRequest['kind'];

/** Какая заявка пришла днём. Днём приходят не только аварии (организаторы,
    22.09), и от типа зависит, что заявке разрешено: авария может
    перестроить остаток дня, обычная встаёт только в свободное окно. */
export type NewOrderWork = 'emergency' | 'connect' | 'local';

export const WORK_TITLES: [NewOrderWork, string][] = [
  ['emergency', 'Авария'],
  ['connect', 'Подключение'],
  ['local', 'Ремонт у клиента'],
];

const WORK_SKILL: Record<NewOrderWork, string> = {
  emergency: 'Аварийные работы',
  connect: 'Работы на подключение и дозаказы',
  local: 'Локальные работы',
};

/** Минут на адресе по нормативу заказчика: базовый норматив минус дорога. */
export const WORK_MINUTES: Record<NewOrderWork, number> = {
  emergency: 80,
  connect: 70,
  local: 30,
};

export interface EventDraft {
  kind: EventKind;
  work: NewOrderWork;
  at: string;
  orderId: string;
  engineerId: string;
  delayMin: number;
  district: string;
  windowStart: string;
  windowEnd: string;
  durationMin: number;
  mode: 'minimal' | 'full';
}

export const KIND_TITLES: [EventKind, string][] = [
  ['urgent_order', 'Новая заявка'],
  ['cancel_order', 'Отмена заявки'],
  ['engineer_unavailable', 'Бригада выбыла'],
  ['engineer_delayed', 'Задержка бригады'],
];

export const EMPTY_DRAFT: EventDraft = {
  kind: 'urgent_order',
  work: 'emergency',
  at: '13:00',
  orderId: '',
  engineerId: '',
  delayMin: 45,
  district: '',
  windowStart: '14:00',
  windowEnd: '18:00',
  durationMin: WORK_MINUTES.emergency,
  mode: 'minimal',
};

/** Чего не хватает, чтобы отправить событие. Пустая строка значит, что всё
    заполнено: кнопка включается только тогда. */
export function whatIsMissing(draft: EventDraft): string {
  if (draft.kind === 'cancel_order' && !draft.orderId) return 'Выберите заявку';
  if (
    (draft.kind === 'engineer_unavailable' || draft.kind === 'engineer_delayed') &&
    !draft.engineerId
  ) {
    return 'Выберите бригаду';
  }
  if (draft.kind === 'urgent_order') {
    if (!draft.district) return 'Выберите район';
    if (draft.windowEnd <= draft.windowStart) return 'Окно должно заканчиваться позже начала';
  }
  return '';
}

/** Точка новой заявки: середина уже известных заявок этого района.

Координат у новой заявки взяться неоткуда, а район диспетчер называет
сразу. Это допущение видно на карте: точка ставится среди соседних заявок.
*/
function districtCenter(plan: PlanPayload, district: string): { lat: number; lon: number } {
  const inDistrict = plan.orders.filter((order) => order.district === district);
  const source = inDistrict.length > 0 ? inDistrict : plan.orders;
  const lat = source.reduce((sum, order) => sum + order.lat, 0) / (source.length || 1);
  const lon = source.reduce((sum, order) => sum + order.lon, 0) / (source.length || 1);
  return { lat, lon };
}

export function toRequest(draft: EventDraft, plan: PlanPayload, apply: boolean): ReplanRequest {
  const base = {
    region: plan.region,
    kind: draft.kind,
    at: draft.at,
    mode: draft.mode,
    apply,
  };

  if (draft.kind === 'cancel_order') return { ...base, order_id: draft.orderId };
  if (draft.kind === 'engineer_unavailable') return { ...base, engineer_id: draft.engineerId };
  if (draft.kind === 'engineer_delayed') {
    return { ...base, engineer_id: draft.engineerId, delay_min: draft.delayMin };
  }

  const point = districtCenter(plan, draft.district);
  const prefix = draft.work === 'emergency' ? 'АВАРИЯ' : 'НОВАЯ';
  const id = `${prefix}-${draft.at.replace(':', '')}`;
  return {
    ...base,
    // Пересобрать остаток дня можно ради аварии, но не ради обычной заявки.
    mode: draft.work === 'emergency' ? draft.mode : 'minimal',
    new_order: {
      id,
      lat: point.lat,
      lon: point.lon,
      address: `${draft.district}, адрес уточняется`,
      district: draft.district,
      duration_min: draft.durationMin,
      window_start: draft.windowStart,
      window_end: draft.windowEnd,
      required_skill: WORK_SKILL[draft.work],
      required_vehicle: null,
    },
  };
}
