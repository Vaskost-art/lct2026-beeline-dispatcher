/** Интерфейс картографического слоя.

Сам слой написан на обычном JavaScript и переехал сюда без переписывания:
это отлаженная работа с Яндекс Картами и собственная схема на случай, когда
ключа нет или сервис не отвечает. Здесь только описание его границы.
*/

export interface MapPoint {
  lat: number;
  lon: number;
  kind?: 'base' | 'stop';
  label?: string;
  title?: string;
  orderId?: string;
  district?: string;
}

export interface MapRoute {
  id: string;
  color: string;
  points: MapPoint[];
}

export interface MapModel {
  routes: MapRoute[];
  loose: MapPoint[];
}

export interface MapOptions {
  apiKey?: string | null;
  theme?: string;
  onFallback?: (why: string) => void;
  onSelectOrder?: (orderId: string) => void;
  onPick?: (lat: number, lon: number) => void;
}

export interface DispatcherMap {
  kind: 'yandex' | 'scheme';
  title: string;
  ready: Promise<unknown>;
  render(model: MapModel): void;
  fit(): void;
  focusOrder(orderId: string | null): void;
  setTheme(theme: string): void;
  setPickMarker(lat: number, lon: number): void;
  clearPickMarker(): void;
  destroy(): void;
}

export function createDispatcherMap(
  container: HTMLElement,
  options?: MapOptions,
): Promise<DispatcherMap>;
