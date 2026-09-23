import { ArrowCounterClockwise, FloppyDisk } from '@phosphor-icons/react';
import { useState } from 'react';

import type { ApiError } from '../../api/client';
import { useRestoreDay, useSaveDay, useSavedDay } from '../../api/queries';
import { Button } from '../../components/Button';

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
  /** Пишет ли сервис версии дня в базу. */
  journal: boolean | undefined;
}

/** Сохранение рабочего дня и возврат к нему.

«Восстановить» заменяет текущий день сохранённым, поэтому спрашивает
подтверждение и называет дату сохранения: одно нажатие не должно молча
подменять смену давним днём. Ошибки показываются здесь же -
иначе неудачное сохранение выглядело как удачное.
*/
export function SaveSection({ open, region, planned, journal }: Props) {
  const saved = useSavedDay(region, open);
  const save = useSaveDay();
  const restore = useRestoreDay();
  const [confirming, setConfirming] = useState(false);
  const failure = (save.error ?? restore.error) as ApiError | null;
  const savedAt = whenSaved(saved.data?.saved_at);

  return (
    <section className="flex flex-col gap-2">
      <h3 className="eyebrow px-2">Сохранение</h3>
      {/* Без базы день живёт до перезапуска сервиса, и узнавать об этом
          после перезапуска поздно. */}
      {journal === false ? (
        <p className="px-2 text-[12px] text-warn">
          База недоступна: день хранится только в памяти сервиса и пропадёт при
          перезапуске. Сохраните его вручную.
        </p>
      ) : null}
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
          onClick={() => setConfirming(true)}
        >
          <ArrowCounterClockwise size={15} weight="bold" aria-hidden />
          Восстановить
        </Button>
      </div>

      {confirming ? (
        <div className="mx-2 flex flex-col gap-2 rounded-md border border-warn bg-warn-soft px-3 py-2">
          <p className="text-[12px] text-ink">
            Текущий день заменится сохранением от {savedAt}. Вернуть его можно
            шагом назад.
          </p>
          <div className="flex gap-2">
            <Button
              variant="primary"
              busy={restore.isPending}
              busyLabel="Восстанавливаем"
              onClick={() => {
                if (region) restore.mutate({ region }, { onSettled: () => setConfirming(false) });
              }}
            >
              Восстановить
            </Button>
            <Button variant="quiet" onClick={() => setConfirming(false)}>
              Отмена
            </Button>
          </div>
        </div>
      ) : null}

      {failure ? (
        <p role="alert" className="px-2 text-[12px] text-danger">
          {failure.message}
        </p>
      ) : (
        <p className="px-2 text-[12px] text-ink-3">
          {save.isSuccess
            ? 'День сохранён.'
            : saved.data?.exists
              ? `Есть сохранение от ${savedAt}.`
              : 'Сохранения пока нет.'}
        </p>
      )}
    </section>
  );
}
