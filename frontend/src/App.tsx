import { Screen } from './features/shell/Screen';
import { DayProvider } from './state/day';

export function App() {
  return (
    <DayProvider>
      <Screen />
    </DayProvider>
  );
}
