/** Состояние экрана диспетчера.

Здесь живёт только то, что принадлежит экрану: выбранный участок, выбранная
заявка, скрытые бригады, открытая панель, оформление. Данные плана держит
TanStack Query, дублировать их сюда незачем.
*/
import { createContext, useContext, useMemo, useReducer, type ReactNode } from 'react';

export type Panel =
  | 'menu'
  | 'compare'
  | 'risk'
  | 'validate'
  | 'pickup'
  | 'shortfall'
  | 'assumptions'
  | 'upload'
  | 'saved';

export type Theme = 'system' | 'light' | 'dark';

const THEME_KEY = 'dispatcher-theme';

interface State {
  region: string | null;
  selectedOrder: string | null;
  hiddenCrews: Set<string>;
  panel: Panel | null;
  theme: Theme;
}

type Action =
  | { type: 'region'; region: string }
  | { type: 'order'; order: string | null }
  | { type: 'crew'; crew: string }
  | { type: 'panel'; panel: Panel | null }
  | { type: 'theme'; theme: Theme };

function readTheme(): Theme {
  // В приватном окне обращение к хранилищу бросает исключение, и экран не
  // должен из-за этого падать.
  try {
    const stored = localStorage.getItem(THEME_KEY);
    return stored === 'light' || stored === 'dark' ? stored : 'system';
  } catch {
    return 'system';
  }
}

function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  if (theme === 'system') root.removeAttribute('data-theme');
  else root.setAttribute('data-theme', theme);
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    // Оформление это удобство: не сохранилось - работаем дальше.
  }
}

function reduce(state: State, action: Action): State {
  switch (action.type) {
    case 'region':
      if (action.region === state.region) return state;
      // Заявка и скрытые бригады принадлежат прежнему участку.
      return { ...state, region: action.region, selectedOrder: null, hiddenCrews: new Set() };
    case 'order':
      return { ...state, selectedOrder: action.order };
    case 'crew': {
      const hidden = new Set(state.hiddenCrews);
      if (!hidden.delete(action.crew)) hidden.add(action.crew);
      return { ...state, hiddenCrews: hidden };
    }
    case 'panel':
      return { ...state, panel: action.panel };
    case 'theme':
      applyTheme(action.theme);
      return { ...state, theme: action.theme };
  }
}

export interface Day extends State {
  selectRegion: (region: string) => void;
  selectOrder: (order: string | null) => void;
  toggleCrew: (crew: string) => void;
  openPanel: (panel: Panel) => void;
  closePanel: () => void;
  setTheme: (theme: Theme) => void;
}

const DayContext = createContext<Day | null>(null);

export function DayProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reduce, null, () => ({
    region: null,
    selectedOrder: null,
    hiddenCrews: new Set<string>(),
    panel: null,
    theme: readTheme(),
  }));

  const value = useMemo<Day>(
    () => ({
      ...state,
      selectRegion: (region) => dispatch({ type: 'region', region }),
      selectOrder: (order) => dispatch({ type: 'order', order }),
      toggleCrew: (crew) => dispatch({ type: 'crew', crew }),
      openPanel: (panel) => dispatch({ type: 'panel', panel }),
      closePanel: () => dispatch({ type: 'panel', panel: null }),
      setTheme: (theme) => dispatch({ type: 'theme', theme }),
    }),
    [state],
  );

  return <DayContext value={value}>{children}</DayContext>;
}

export function useDay(): Day {
  const day = useContext(DayContext);
  if (!day) throw new Error('useDay вызван вне DayProvider');
  return day;
}
