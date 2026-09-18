/** Корневой экран диспетчера. */
export function App() {
  return (
    <div className="flex h-full flex-col">
      <header className="border-b border-line bg-panel px-4 py-3">
        <h1 className="text-base font-semibold">Планировщик выездных работ</h1>
        <p className="text-muted">
          распределение заявок, маршруты и перепланирование дня
        </p>
      </header>
    </div>
  );
}
