import { List } from '@phosphor-icons/react';

import { Button } from '../../components/Button';
import type { RegionSummary } from '../../api/types';

interface Props {
  regions: RegionSummary[];
  region: string | null;
  onRegion: (region: string) => void;
  onMenu: () => void;
  onPlan: () => void;
  busy: boolean;
}

/** Шапка: меню, выбор участка и единственная кнопка расчёта.

Выбора способа расчёта здесь нет: диспетчеру нужен лучший план, а не список
из трёх способов его посчитать. Три способа живут в окне сравнения.
*/
export function Header({ regions, region, onRegion, onMenu, onPlan, busy }: Props) {
  return (
    <header className="flex flex-wrap items-center gap-3 border-b border-line bg-panel px-4 py-3">
      <Button onClick={onMenu} aria-label="Меню">
        <List size={18} />
        <span className="hidden sm:inline">Меню</span>
      </Button>

      <div className="min-w-0">
        <h1 className="truncate text-base font-semibold">Планировщик выездных работ</h1>
        <p className="hidden truncate text-xs text-muted sm:block">
          распределение заявок, маршруты и перепланирование дня
        </p>
      </div>

      <div className="ml-auto flex min-w-0 items-center gap-2">
        <select
          aria-label="Участок"
          className="min-w-0 rounded-md border border-line bg-panel px-2 py-2 text-sm"
          value={region ?? ''}
          onChange={(event) => onRegion(event.target.value)}
        >
          <option value="" disabled>
            Выберите участок
          </option>
          {regions.map((item) => (
            <option key={item.region_key} value={item.region_key}>
              {item.region_name}
            </option>
          ))}
        </select>

        <Button variant="primary" onClick={onPlan} busy={busy} disabled={!region}>
          Спланировать
        </Button>
      </div>
    </header>
  );
}
