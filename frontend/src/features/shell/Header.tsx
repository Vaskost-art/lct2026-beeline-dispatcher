import { CaretDown, List } from '@phosphor-icons/react';

import { Button } from '../../components/Button';
import type { RegionSummary } from '../../api/types';

interface Props {
  regions: RegionSummary[];
  region: string | null;
  onRegion: (region: string) => void;
  onMenu: () => void;
  onPlan: () => void;
  busy: boolean;
  planned: boolean;
}

/** Оболочка смены: меню, участок, единственное действие.

Выбора способа расчёта здесь нет: диспетчеру нужен лучший план, а не список
из трёх способов его посчитать. Три способа живут в окне сравнения.
*/
export function Header({ regions, region, onRegion, onMenu, onPlan, busy, planned }: Props) {
  const current = regions.find((item) => item.region_key === region);

  return (
    <header className="flex h-12 shrink-0 items-center gap-3 bg-shell px-3 text-shell-ink">
      <Button variant="shell" onClick={onMenu} aria-label="Меню">
        <List size={16} weight="bold" />
        <span className="hidden sm:inline">Меню</span>
      </Button>

      <span className="hidden min-w-0 items-baseline gap-2 md:flex">
        <span className="truncate text-[13px] font-semibold tracking-[-0.01em]">
          Планировщик выездных работ
        </span>
        <span className="truncate text-[11px] text-shell-muted">смена на сегодня</span>
      </span>

      <div className="ml-auto flex min-w-0 items-center gap-2">
        <div className="relative min-w-0">
          <select
            aria-label="Участок"
            value={region ?? ''}
            onChange={(event) => onRegion(event.target.value)}
            className="h-8 w-full min-w-0 appearance-none rounded-md border border-white/12 bg-transparent
                       py-0 pl-3 pr-8 text-[13px] font-medium text-shell-ink hover:bg-white/8"
          >
            <option value="" disabled>
              Выберите участок
            </option>
            {regions.map((item) => (
              <option key={item.region_key} value={item.region_key} className="text-ink">
                {item.region_name}
              </option>
            ))}
          </select>
          <CaretDown
            size={12}
            weight="bold"
            aria-hidden
            className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-shell-muted"
          />
        </div>

        {current ? (
          <span className="hidden whitespace-nowrap text-[11px] text-shell-muted lg:inline tnum">
            {current.orders} заявок · {current.engineers} бригад
          </span>
        ) : null}

        <Button
          variant="primary"
          data-testid="plan"
          onClick={onPlan}
          busy={busy}
          disabled={!region}
        >
          {planned ? 'Пересчитать' : 'Спланировать'}
        </Button>
      </div>
    </header>
  );
}
