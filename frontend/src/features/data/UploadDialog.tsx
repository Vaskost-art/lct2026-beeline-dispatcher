import { UploadSimple } from '@phosphor-icons/react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';

import { ApiError } from '../../api/client';
import type { RegionSummary } from '../../api/types';
import { Button } from '../../components/Button';
import { Modal } from '../../components/Modal';

interface Props {
  open: boolean;
  onClose: () => void;
  onLoaded: (region: string) => void;
}

interface UploadAnswer {
  region: string;
  format: string;
  summary: RegionSummary;
  events: unknown[];
}

/** Загрузка своего набора данных.

Отказ показывается здесь же, в форме: сообщение сервиса называет строку и
колонку, в которой он споткнулся, и это готовый текст для человека.
*/
export function UploadDialog({ open, onClose, onLoaded }: Props) {
  const picker = useRef<HTMLInputElement>(null);
  const [name, setName] = useState('');
  const client = useQueryClient();

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const query = new URLSearchParams({ filename: file.name, name });
      const answer = await fetch(`/api/dataset/upload?${query.toString()}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/octet-stream' },
        body: await file.arrayBuffer(),
      });
      const body = (await answer.json().catch(() => null)) as
        | { ok: boolean; data?: UploadAnswer; error?: { code: string; message: string } }
        | null;
      if (!answer.ok || !body || body.ok !== true || !body.data) {
        throw new ApiError(
          body?.error?.code ?? 'error',
          body?.error?.message ?? 'Не удалось прочитать файл',
        );
      }
      return body.data;
    },
    onSuccess: (data) => {
      // Список участков изменился: в нём появился загруженный.
      void client.invalidateQueries({ queryKey: ['meta'] });
      onLoaded(data.region);
    },
  });

  return (
    <Modal open={open} title="Загрузить свой набор данных" onClose={onClose}>
      <div className="flex flex-col gap-3">
        <p className="text-[13px] text-ink-2">
          Подойдёт выгрузка заявок в CSV или набор в JSON, который сервис отдаёт при
          выгрузке. Один рабочий день: до сотни заявок и полутора десятков бригад.
        </p>

        <label className="flex min-w-0 flex-col gap-1">
          <span className="eyebrow">Как назвать участок</span>
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="например, Северный участок"
            className="h-8 w-full rounded-md border border-line bg-panel px-2 text-[13px]"
          />
        </label>

        <input
          ref={picker}
          type="file"
          accept=".csv,.json,text/csv,application/json"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) upload.mutate(file);
          }}
        />

        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="primary"
            busy={upload.isPending}
            busyLabel="Читаем файл"
            onClick={() => picker.current?.click()}
          >
            <UploadSimple size={15} weight="bold" aria-hidden />
            Выбрать файл
          </Button>
          {upload.data ? (
            <span className="text-[13px] text-ink-2 tnum">
              Загружено: {upload.data.summary.orders} заявок,{' '}
              {upload.data.summary.engineers} бригад.
            </span>
          ) : null}
        </div>

        {upload.error ? (
          <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-[13px] text-ink">
            {(upload.error as ApiError).message}
          </p>
        ) : null}
      </div>
    </Modal>
  );
}
