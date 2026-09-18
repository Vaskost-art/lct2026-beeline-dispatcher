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
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/45 backdrop-blur-[1px]" />
        <Dialog.Content
          className="fixed left-1/2 top-1/2 z-50 flex max-h-[84vh] w-[min(720px,92vw)] -translate-x-1/2
                     -translate-y-1/2 flex-col overflow-hidden rounded-lg border border-line bg-panel
                     shadow-[0_16px_48px_rgb(10_14_20/0.24)]"
        >
          <div className="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-line px-4">
            <Dialog.Title className="text-[15px] font-semibold tracking-[-0.01em]">
              {title}
            </Dialog.Title>
            <Dialog.Close
              aria-label="Закрыть"
              className="rounded-md p-1 text-ink-3 hover:bg-raised hover:text-ink"
            >
              <X size={18} />
            </Dialog.Close>
          </div>
          <div
            className="min-h-0 flex-1 overflow-auto px-4 py-4
                       [mask-image:linear-gradient(to_bottom,black_calc(100%-20px),transparent)]"
          >
            {children}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
