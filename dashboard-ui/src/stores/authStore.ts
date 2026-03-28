import { create } from 'zustand';
import type { User, Role } from '../types/auth';
import { ROLE_WRITE_ACCESS } from '../lib/constants';

interface AuthState {
  user: User | null;
  token: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  login: (token: string, refreshToken: string, user: User) => void;
  logout: () => void;
  hasRole: (roles: Role[]) => boolean;
  hasWriteAccess: (action: string) => boolean;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: JSON.parse(localStorage.getItem('a1-user') || 'null'),
  token: localStorage.getItem('a1-token'),
  refreshToken: localStorage.getItem('a1-refresh-token'),
  isAuthenticated: !!localStorage.getItem('a1-token'),

  login: (token, refreshToken, user) => {
    localStorage.setItem('a1-token', token);
    localStorage.setItem('a1-refresh-token', refreshToken);
    localStorage.setItem('a1-user', JSON.stringify(user));
    set({ token, refreshToken, user, isAuthenticated: true });
  },

  logout: () => {
    localStorage.removeItem('a1-token');
    localStorage.removeItem('a1-refresh-token');
    localStorage.removeItem('a1-user');
    set({ token: null, refreshToken: null, user: null, isAuthenticated: false });
  },

  hasRole: (roles) => {
    const user = get().user;
    return !!user && roles.includes(user.role);
  },

  hasWriteAccess: (action) => {
    const user = get().user;
    if (!user) return false;
    const allowed = ROLE_WRITE_ACCESS[action];
    return allowed ? allowed.includes(user.role) : false;
  },
}));
