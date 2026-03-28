// Design tokens — single source of truth for colours, spacing, and status styles

export const COLORS = [
  '#3b82f6',
  '#8b5cf6',
  '#10b981',
  '#f59e0b',
  '#ef4444',
  '#ec4899',
  '#06b6d4',
  '#84cc16',
];

export const STATUS_COLORS: Record<string, string> = {
  healthy: '#10b981',
  unhealthy: '#ef4444',
  pending: '#f59e0b',
  running: '#3b82f6',
  completed: '#10b981',
  failed: '#ef4444',
  warning: '#f59e0b',
  success: '#10b981',
  error: '#ef4444',
  info: '#3b82f6',
  local: '#10b981',
  external: '#3b82f6',
};

export const SPACING = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
} as const;

export const STATUS_TAG_CONFIG: Record<string, { color: string; label?: string }> = {
  local: { color: 'green', label: 'LOCAL' },
  external: { color: 'blue', label: 'EXT' },
  pending: { color: 'default' },
  running: { color: 'processing' },
  completed: { color: 'success' },
  failed: { color: 'error' },
  healthy: { color: 'success' },
  unhealthy: { color: 'error' },
  blocked: { color: 'warning' },
  cancelled: { color: 'default' },
};

/** Latency threshold above which a value is considered slow (ms) */
export const LATENCY_WARN_MS = 5000;
