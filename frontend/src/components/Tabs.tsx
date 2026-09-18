interface Item {
  key: string;
  title: string;
  count?: number;
}

interface Props {
  items: Item[];
  value: string;
  onChange: (key: string) => void;
}

export function Tabs({ items, value, onChange }: Props) {
  return (
    <div role="tablist" className="flex gap-1 border-b border-line">
      {items.map((item) => (
        <button
          key={item.key}
          role="tab"
          type="button"
          aria-selected={item.key === value}
          onClick={() => onChange(item.key)}
          className={
            'min-w-0 truncate px-3 py-2 text-sm ' +
            (item.key === value
              ? 'border-b-2 border-accent font-medium text-text'
              : 'text-muted hover:text-text')
          }
        >
          {item.title}
          {item.count === undefined ? null : (
            <span className="ml-1 text-muted">{item.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}
