import * as Dialog from '@radix-ui/react-dialog';
import { X } from '@phosphor-icons/react';
import type { ReactNode } from 'react';

interface Props {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}

/** Модальное окно на Radix: фокус, Escape и возврат фокуса при закрытии
    достаются готовыми, писать их руками незачем. */
export function Modal({ open, title, onClose, children }: Props) {
  return (
    <Dialog.Root open={open} onOpenChange={(next) => !next && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content
          className="fixed left-1/2 top-1/2 max-h-[85vh] w-[min(920px,94vw)] -translate-x-1/2
                     -translate-y-1/2 overflow-auto rounded-xl border border-line bg-panel p-5"
        >
          <div className="mb-3 flex items-start justify-between gap-4">
            <Dialog.Title className="text-base font-semibold">{title}</Dialog.Title>
            <Dialog.Close aria-label="Закрыть" className="rounded p-1 hover:bg-bg">
              <X size={18} />
            </Dialog.Close>
          </div>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
