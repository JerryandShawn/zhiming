import { create } from 'zustand';
export type Theme = 'system' | 'light' | 'dark';

function storedTheme(): Theme {
  try {
    const value = localStorage.getItem('mingjing-theme');
    if (value === 'light' || value === 'dark') return value;
  } catch {
    /* Storage is optional, including in private browsing. */
  }
  return 'system';
}

export function applyTheme(value: Theme) {
  const actual =
    value === 'system' ? (window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light') : value;
  document.documentElement.dataset.theme = actual;
}

type UiState = { theme: Theme; setTheme: (value: Theme) => void; toast: string; notify: (message?: string) => void };
export const useUi = create<UiState>((set) => ({
  theme: storedTheme(),
  setTheme: (theme) => {
    let selected = theme;
    try {
      localStorage.setItem('mingjing-theme', theme);
    } catch {
      selected = 'system';
    }
    applyTheme(selected);
    set({ theme: selected });
  },
  toast: '',
  notify: (toast = '这是合成界面预览，你的资料没有改动。') => set({ toast }),
}));
