/** Сборка того, что карте нужно нарисовать.

Карта ничего не знает ни про заявки, ни про смены: только точки, линии и
подписи. Поэтому модель собирается здесь и проверяется без браузера.
*/
import type { PlanPayload } from '../../api/types';
import type { MapModel, MapPoint } from './map';

/** Цвет бригады: равномерно разнесённые оттенки, устойчивые между
    перерисовками, чтобы бригада не меняла цвет на каждом расчёте. */
export function crewColor(index: number): string {
  return `hsl(${Math.round((index * 137.508) % 360)} 72% 58%)`;
}

export function buildMapModel(plan: PlanPayload, hiddenCrews: Set<string>): MapModel {
  const orders = new Map(plan.orders.map((order) => [order.id, order]));
  const engineers = new Map(plan.engineers.map((engineer) => [engineer.id, engineer]));

  const routes = [];
  let index = 0;
  for (const route of plan.routes) {
    const color = crewColor(index);
    index += 1;
    if (hiddenCrews.has(route.engineer_id)) continue;

    const points: MapPoint[] = [];
    const engineer = engineers.get(route.engineer_id);
    if (engineer) {
      points.push({
        lat: engineer.lat,
        lon: engineer.lon,
        kind: 'base',
        title: `${engineer.name} · база участка\nСмена ${engineer.shift_text} · ${engineer.vehicle}`,
      });
    }

    route.stops.forEach((stop, position) => {
      const order = orders.get(stop.order_id);
      if (!order) return;
      points.push({
        lat: order.lat,
        lon: order.lon,
        kind: 'stop',
        label: String(position + 1),
        orderId: order.id,
        district: order.district,
        title: `${stop.start}–${stop.end} · ${route.engineer_id}\n${order.district}, ${order.address}`,
      });
    });

    if (points.length > 1) routes.push({ id: route.engineer_id, color, points });
  }

  const reasons = new Map(plan.unassigned.map((item) => [item.order_id, item.reason_text]));
  const loose: MapPoint[] = plan.orders
    .filter((order) => reasons.has(order.id))
    .map((order) => ({
      lat: order.lat,
      lon: order.lon,
      orderId: order.id,
      district: order.district,
      title: `Заявка ${order.id} — не назначена\n${reasons.get(order.id) ?? ''}`,
    }));

  return { routes, loose };
}
