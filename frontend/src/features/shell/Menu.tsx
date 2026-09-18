import {
  ArrowCounterClockwise,
  ScalesIcon,
  ClipboardText,
  DownloadSimple,
  FloppyDisk,
  Info,
  UploadSimple,
} from '@phosphor-icons/react';

import { useRestoreDay, useSaveDay, useSavedDay } from '../../api/queries';
import { Button } from '../../components/Button';
import { Drawer } from '../../components/Drawer';
import type { Panel, Theme } from '../../state/day';

/** «2026-09-18T13:03:59» человек не читает: показываем время словами. */
function whenSaved(stamp: string | undefined): string {
  if (!stamp) return 'неизвестно когда';
  const at = new Date(stamp);
  if (Number.isNaN(at.getTime())) return stamp;
  return at.toLocaleString('ru-RU', {
    day: 'numeric',
    month: 'long',
    hour: '2-digit',
    minute: '2-digit',
  });
}

interface Props {
  open: boolean;
  region: string | null;
  planned: boolean;
  theme: Theme;
  onTheme: (theme: Theme) => void;
  onPanel: (panel: Panel) => void;
  onClose: () => void;
}

const THEMES: [Theme, string][] = [
  ['system', 'Как в системе'],
  ['light', 'День'],
  ['dark', 'Ночь'],
];

function Item({
  icon: Icon,
  title,
  hint,
  disabled,
  onClick,
}: {
  icon: typeof Info;
  title: string;
  hint: string;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="flex w-full items-start gap-3 rounded-md px-2 py-2 text-left
                 transition-colors duration-[120ms] hover:bg-raised
                 disabled:cursor-not-allowed disabled:opacity-45"
    >
      <Icon size={17} weight="duotone" aria-hidden className="mt-0.5 shrink-0 text-ink-3" />
      <span className="min-w-0">
        <span className="block text-[13px] font-medium">{title}</span>
        <span className="block text-[12px] text-ink-3">{hint}</span>
      </span>
    </button>
  );
}

/** Меню смены: всё, что не нужно постоянно на глазах. */
export function Menu({ open, region, planned, theme, onTheme, onPanel, onClose }: Props) {
  const saved = useSavedDay(region, open);
  const save = useSaveDay();
  const restore = useRestoreDay();

  const go = (panel: Panel) => {
    onClose();
    onPanel(panel);
  };

  return (
    <Drawer open={open} title="Инструменты дня" onClose={onClose}>
      <nav className="flex flex-col gap-4">
        <section className="sm:hidden">
          <h3 className="eyebrow mb-1 px-2">Проверки</h3>
          <Item
            icon={Info}
            title="Проверить план"
            hint="окна, смены, навыки и транспорт заново"
            disabled={!planned}
            onClick={() => go('validate')}
          />
          <Item
            icon={Info}
            title="Прогноз опозданий"
            hint="где план сломается от первой задержки"
            disabled={!planned}
            onClick={() => go('risk')}
          />
          <Item
            icon={Info}
            title="Что взять в офисе"
            hint="ведомость на выдачу по бригадам"
            disabled={!planned}
            onClick={() => go('pickup')}
          />
        </section>

        <section>
          <h3 className="eyebrow mb-1 px-2">Разбор</h3>
          <Item
            icon={ScalesIcon}
            title="Сравнить способы расчёта"
            hint="базовый вариант из ТЗ, быстрый и оптимальный"
            disabled={!planned}
            onClick={() => go('compare')}
          />
        </section>

        <section>
          <h3 className="eyebrow mb-1 px-2">Данные</h3>
          <Item
            icon={ClipboardText}
            title="Как считаем"
            hint="допущения, принятые за отсутствующие данные"
            onClick={() => go('assumptions')}
          />
          <Item
            icon={UploadSimple}
            title="Загрузить свой набор"
            hint="выгрузка заявок в CSV или набор в JSON"
            onClick={() => go('upload')}
          />
          <Item
            icon={DownloadSimple}
            title="Выгрузить план"
            hint="файл в формате технического задания"
            disabled={!region || !planned}
            onClick={() => {
              if (region) window.open(`/api/export/${region}`, '_blank');
            }}
          />
        </section>

        <section className="flex flex-col gap-2">
          <h3 className="eyebrow px-2">Сохранение</h3>
          <div className="flex flex-wrap gap-2 px-2">
            <Button
              variant="quiet"
              disabled={!region || !planned}
              busy={save.isPending}
              busyLabel="Сохраняем"
              onClick={() => {
                if (region) save.mutate({ region, name: 'Рабочий день' });
              }}
            >
              <FloppyDisk size={15} weight="bold" aria-hidden />
              Сохранить день
            </Button>
            <Button
              variant="quiet"
              disabled={!region || !saved.data?.exists}
              busy={restore.isPending}
              busyLabel="Восстанавливаем"
              onClick={() => {
                if (region) restore.mutate({ region });
              }}
            >
              <ArrowCounterClockwise size={15} weight="bold" aria-hidden />
              Восстановить
            </Button>
          </div>
          <p className="px-2 text-[12px] text-ink-3">
            {save.isSuccess
              ? 'День сохранён.'
              : saved.data?.exists
                ? `Есть сохранение от ${whenSaved(saved.data.saved_at)}.`
                : 'Сохранения пока нет.'}
          </p>
        </section>

        <section>
          <h3 className="eyebrow mb-1 px-2">Оформление</h3>
          <div className="flex gap-1 px-2">
            {THEMES.map(([key, title]) => (
              <button
                key={key}
                type="button"
                aria-pressed={theme === key}
                onClick={() => onTheme(key)}
                className={
                  'h-8 flex-1 rounded-md border text-[12px] transition-colors duration-[120ms] ' +
                  (theme === key
                    ? 'border-accent bg-accent-soft font-medium text-ink'
                    : 'border-line text-ink-3 hover:text-ink')
                }
              >
                {title}
              </button>
            ))}
          </div>
        </section>
      </nav>
    </Drawer>
  );
}
