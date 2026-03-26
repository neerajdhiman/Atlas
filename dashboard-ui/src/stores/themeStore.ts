import { create } from 'zustand';

interface ThemeState {
  isDark: boolean;
  toggle: () => void;
}

export const useThemeStore = create<ThemeState>((set) => ({
  isDark: localStorage.getItem('a1-theme') !== 'light',
  toggle: () =>
    set((state) => {
      const next = !state.isDark;
      localStorage.setItem('a1-theme', next ? 'dark' : 'light');
      return { isDark: next };
    }),
}));
