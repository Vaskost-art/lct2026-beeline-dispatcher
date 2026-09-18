import * as Dialog from '@radix-ui/react-dialog';
import { X } from '@phosphor-icons/react';
import type { ReactNode } from 'react';

interface Props {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}

/** Выдвижная панель слева: держит всё, что не нужно постоянно на глазах. */
export function Drawer({ open, title, onClose, children }: Props) {
  return (
    <Dialog.Root open={open} onOpenChange={(next) => !next && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/45 backdrop-blur-[1px]" />
        <Dialog.Content
          className="fixed inset-y-0 left-0 flex w-[min(360px,88vw)] flex-col gap-4
                     overflow-auto border-r border-line bg-panel p-4 shadow-[0_0_48px_rgb(10_14_20/0.24)]"
        >
          <div className="flex items-start justify-between gap-4">
            <Dialog.Title className="text-[15px] font-semibold tracking-[-0.01em]">{title}</Dialog.Title>
            <Dialog.Close aria-label="Закрыть меню" className="rounded-md p-1 text-ink-3 hover:bg-raised hover:text-ink">
              <X size={18} />
            </Dialog.Close>
          </div>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
