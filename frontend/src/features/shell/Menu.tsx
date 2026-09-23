import {
  ArrowUUpLeft,
  ScalesIcon,
  ClipboardText,
  DownloadSimple,
  Info,
  ShieldCheck,
  Timer,
  Toolbox,
  UploadSimple,
} from '@phosphor-icons/react';

import { Drawer } from '../../components/Drawer';
import type { Panel, Theme } from '../../state/day';
import { SaveSection } from './SaveSection';

interface Props {
  open: boolean;
  region: string | null;
  planned: boolean;
  /** Пишет ли сервис версии дня в базу; до ответа сервиса неизвестно. */
  journal?: boolean;
  theme: Theme;
  onTheme: (theme: Theme) => void;
  onPanel: (panel: Panel) => void;
  onClose: () => void;
  /** Что отменит шаг назад, если есть что отменять. */
  undoLabel?: string;
  onUndo?: () => void;
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
export function Menu({
  open,
  region,
  planned,
  journal,
  theme,
  onTheme,
  onPanel,
  onClose,
  undoLabel,
  onUndo,
}: Props) {
  const go = (panel: Panel) => {
    onClose();
    onPanel(panel);
  };

  return (
    <Drawer open={open} title="Инструменты дня" onClose={onClose}>
      <nav className="flex flex-col gap-4">
        <section className="sm:hidden">
          <h3 className="eyebrow mb-1 px-2">Проверки</h3>
          {/* На телефоне кнопок сводки нет, а откатить ошибочную отметку
              нужно и там. */}
          {undoLabel && onUndo ? (
            <Item
              icon={ArrowUUpLeft}
              title="Шаг назад"
              hint={`отменить: ${undoLabel}`}
              onClick={() => {
                onClose();
                onUndo();
              }}
            />
          ) : null}
          <Item
            icon={ShieldCheck}
            title="Проверить план"
            hint="окна, смены, навыки и транспорт заново"
            disabled={!planned}
            onClick={() => go('validate')}
          />
          <Item
            icon={Timer}
            title="Прогноз опозданий"
            hint="где план сломается от первой задержки"
            disabled={!planned}
            onClick={() => go('risk')}
          />
          <Item
            icon={Toolbox}
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

        <SaveSection open={open} region={region} planned={planned} journal={journal} />

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
