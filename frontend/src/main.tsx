import { MutationCache, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { ApiError } from './api/client';
import { App } from './App';
import './index.css';

// Расчёт дорогой, а данные дня живут ровно столько, сколько открыт экран:
// перезапрашивать их при каждом возврате в окно незачем.
const client: QueryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, retry: false } },
  // День изменился, пока шло действие (другая вкладка, долгий расчёт):
  // сервис отказал, и экран подтягивает свежий план, а не остаётся на старом.
  mutationCache: new MutationCache({
    onError: (error) => {
      if (error instanceof ApiError && error.code === 'day_changed') {
        void client.invalidateQueries({ queryKey: ['plan'] });
      }
    },
  }),
});

const root = document.getElementById('root');
if (root) {
  createRoot(root).render(
    <StrictMode>
      <QueryClientProvider client={client}>
        <App />
      </QueryClientProvider>
    </StrictMode>,
  );
}
