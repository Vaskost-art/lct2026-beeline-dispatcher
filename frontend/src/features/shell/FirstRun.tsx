import { MapTrifold } from '@phosphor-icons/react';

import { Button } from '../../components/Button';

import type { RegionSummary } from '../../api/types';
import { plural } from '../../text';

/** Экран до первого плана: говорит, что это за место, и даёт действие.
    Серая надпись «нет данных» такой работы не делает. */
export function FirstRun({
  region,
  loading,
  regions,
  onRegion,
  onPlan,
  onUpload,
}: {
  region: string | null;
  loading: boolean;
  regions: RegionSummary[];
  onRegion: (region: string) => void;
  onPlan: () => void;
  onUpload: () => void;
}) {
  const current = regions.find((item) => item.region_key === region);

  return (
    <div className="flex min-h-0 flex-1 justify-center rounded-lg border border-line bg-panel pt-[12vh]">
      <div className="flex w-full max-w-[44ch] flex-col items-center gap-4 px-6 py-12 text-center">
        <MapTrifold size={32} weight="duotone" aria-hidden className="text-ink-3" />
        <h2 className="text-[17px] font-semibold tracking-[-0.015em]">
          {/* Во время расчёта заголовок «не построен» врёт: план как раз
              строится. Съёмка ловила эту надпись и снимала уже готовый план. */}
          {loading
            ? 'Считаем план на день'
            : region
              ? 'План на сегодня ещё не построен'
              : 'Смена не выбрана'}
        </h2>
        <p className="text-[13px] leading-relaxed text-ink-3">
          {loading
            ? 'Перебираем варианты: разложить сотню заявок по бригадам так, чтобы '
                + 'сошлись окна клиентов и смены, занимает от сорока секунд до двух минут.'
            : region
              ? 'Сервис разложит заявки по бригадам, покажет маршруты на карте и назовёт причину по каждой заявке, которая не поместилась.'
              : 'Возьмите участок из выгрузки организаторов или загрузите свой файл с заявками.'}
        </p>

        {/* Что сервис берёт в работу. Пустой экран перед расчётом - первое,
            что видит человек, и он должен видеть свой день, а не приглашение
            нажать кнопку. */}
        {current && !loading ? (
          <dl className="grid w-full grid-cols-3 gap-3 rounded-md border border-line bg-raised
                         px-4 py-3 text-left">
            {[
              ['Заявок на день', current.orders],
              ['Бригад на участке', current.engineers],
              ['Срочных', current.urgent],
            ].map(([title, value]) => (
              <div key={String(title)} className="flex min-w-0 flex-col">
                <dt className="eyebrow">{title}</dt>
                <dd className="text-[20px] font-semibold leading-tight tnum">{value}</dd>
              </div>
            ))}
          </dl>
        ) : null}

        {region ? (
          <Button variant="primary" onClick={onPlan} busy={loading}>
            Спланировать день
          </Button>
        ) : (
          <div className="flex w-full flex-col gap-2">
            {regions.map((item) => (
              <Button key={item.region_key} onClick={() => onRegion(item.region_key)}>
                <span className="flex-1 text-left">{item.region_name}</span>
                <span className="text-[12px] text-ink-3 tnum">
                  {item.orders} {plural(item.orders, 'заявка', 'заявки', 'заявок')} ·{' '}
                  {item.engineers} {plural(item.engineers, 'бригада', 'бригады', 'бригад')}
                </span>
              </Button>
            ))}
            <Button variant="quiet" onClick={onUpload}>
              Загрузить свой набор данных
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
