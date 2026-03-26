const BASE = '';

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

// Overview
export const getOverview = () => fetchJson<any>('/admin/overview');
export const getMetrics = () => fetchJson<any>('/admin/metrics');

// Conversations
export const getConversations = (limit = 50, offset = 0) =>
  fetchJson<any>(`/admin/conversations?limit=${limit}&offset=${offset}`);
export const getConversation = (id: string) =>
  fetchJson<any>(`/admin/conversations/${id}`);
export const addFeedback = (convId: string, messageId: string, value: number) =>
  fetchJson<any>(
    `/admin/conversations/${convId}/feedback?message_id=${messageId}&value=${value}`,
    { method: 'POST' }
  );

// Routing
export const getRoutingDecisions = (limit = 100) =>
  fetchJson<any>(`/admin/routing/decisions?limit=${limit}`);
export const getRoutingPerformance = (taskType?: string) =>
  fetchJson<any>(`/admin/routing/performance${taskType ? `?task_type=${taskType}` : ''}`);

// Providers
export const getProviders = () => fetchJson<any>('/admin/providers');
export const refreshProviders = () =>
  fetchJson<any>('/admin/providers/refresh', { method: 'POST' });

// Training
export const getTrainingRuns = (limit = 50) =>
  fetchJson<any>(`/admin/training/runs?limit=${limit}`);
export const getTrainingRun = (id: string) =>
  fetchJson<any>(`/admin/training/runs/${id}`);
export const createTrainingRun = (config: any) =>
  fetchJson<any>('/admin/training/runs', {
    method: 'POST',
    body: JSON.stringify(config),
  });

// Import
export const triggerPaperclipImport = (apiUrl: string, apiKey?: string) =>
  fetchJson<any>(
    `/admin/import/paperclip?api_url=${encodeURIComponent(apiUrl)}${apiKey ? `&api_key=${apiKey}` : ''}`,
    { method: 'POST' }
  );

// Models
export const getModels = () => fetchJson<any>('/v1/models');

// WebSocket live feed
export function connectLiveFeed(onMessage: (event: any) => void): WebSocket {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${protocol}//${window.location.host}/admin/ws/live-feed`);
  ws.onmessage = (e) => onMessage(JSON.parse(e.data));
  return ws;
}
