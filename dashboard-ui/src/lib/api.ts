import axios from 'axios';
import { message } from 'antd';
import { useAuthStore } from '../stores/authStore';

const api = axios.create({
  baseURL: '',
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
});

// Request interceptor: add auth token
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor: global error handling
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().logout();
    } else if (error.code !== 'ERR_CANCELED') {
      const msg =
        error.response?.data?.detail ||
        error.response?.data?.message ||
        error.message ||
        'An unexpected error occurred';
      message.error(String(msg));
    }
    return Promise.reject(error);
  }
);

// --- Overview ---
export const getOverview = () => api.get('/admin/overview').then((r) => r.data);
export const getMetrics = () => api.get('/admin/metrics').then((r) => r.data);

// --- Conversations ---
export const getConversations = (params: {
  limit?: number;
  offset?: number;
  search?: string;
  source?: string;
  date_from?: string;
  date_to?: string;
}) => api.get('/admin/conversations', { params }).then((r) => r.data);

export const getConversation = (id: string) =>
  api.get(`/admin/conversations/${id}`).then((r) => r.data);

export const getConversationStats = () =>
  api.get('/admin/conversations/stats').then((r) => r.data);

export const addFeedback = (convId: string, messageId: string, value: number) =>
  api.post(`/admin/conversations/${convId}/feedback`, null, {
    params: { message_id: messageId, value },
  }).then((r) => r.data);

// --- Routing ---
export const getRoutingDecisions = (params: {
  limit?: number;
  offset?: number;
  provider?: string;
  task_type?: string;
  strategy?: string;
  date_from?: string;
  date_to?: string;
}) => api.get('/admin/routing/decisions', { params }).then((r) => r.data);

export const getRoutingPerformance = (taskType?: string) =>
  api.get('/admin/routing/performance', { params: taskType ? { task_type: taskType } : {} }).then((r) => r.data);

// --- Providers ---
export const getProviders = () => api.get('/admin/providers').then((r) => r.data);
export const refreshProviders = () => api.post('/admin/providers/refresh').then((r) => r.data);

// --- Training ---
export const getTrainingRuns = (limit = 50) =>
  api.get('/admin/training/runs', { params: { limit } }).then((r) => r.data);
export const getTrainingRun = (id: string) =>
  api.get(`/admin/training/runs/${id}`).then((r) => r.data);
export const createTrainingRun = (config: any) =>
  api.post('/admin/training/runs', config).then((r) => r.data);

// --- Import ---
export const triggerPaperclipImport = (apiUrl: string, apiKey?: string) =>
  api.post('/admin/import/paperclip', null, {
    params: { api_url: apiUrl, ...(apiKey ? { api_key: apiKey } : {}) },
  }).then((r) => r.data);

// --- Models ---
export const getModels = () => api.get('/v1/models').then((r) => r.data);

// --- Settings ---
export const getSettings = () => api.get('/admin/settings').then((r) => r.data);
export const saveSettings = (settings: any) => api.put('/admin/settings', settings).then((r) => r.data);

// --- Auth ---
export const loginApi = (username: string, password: string) =>
  api.post('/admin/auth/login', { username, password }).then((r) => r.data);
export const refreshTokenApi = (refreshToken: string) =>
  api.post('/admin/auth/refresh', { refresh_token: refreshToken }).then((r) => r.data);
export const getCurrentUser = () => api.get('/admin/auth/me').then((r) => r.data);

// --- Argilla ---
export const getArgillaStatus = () => api.get('/admin/argilla/status').then((r) => r.data);
export const exportToArgilla = (datasetName: string) =>
  api.post('/admin/argilla/export', null, { params: { dataset_name: datasetName } }).then((r) => r.data);
export const importFromArgilla = (datasetName: string) =>
  api.post('/admin/argilla/import', null, { params: { dataset_name: datasetName } }).then((r) => r.data);

// --- Enhanced Analytics ---
export const getTokenTimeseries = () => api.get('/admin/analytics/token-timeseries').then((r) => r.data);
export const getCostTimeseries = () => api.get('/admin/analytics/cost-timeseries').then((r) => r.data);
export const getRequestHeatmap = () => api.get('/admin/analytics/request-heatmap').then((r) => r.data);
export const getModelLeaderboard = () => api.get('/admin/analytics/model-leaderboard').then((r) => r.data);
export const getRecentRequests = (limit = 50) =>
  api.get('/admin/analytics/recent-requests', { params: { limit } }).then((r) => r.data);
export const getServerStatus = () => api.get('/admin/servers').then((r) => r.data);

// --- Playground ---
export const runPlayground = (data: {
  model: string; prompt: string; system_prompt?: string;
  temperature?: number; max_tokens?: number;
}) => api.post('/admin/playground', data, { timeout: 120000 }).then((r) => r.data);

// --- Distillation ---
export const getDistillationOverview = () => api.get('/admin/distillation/overview').then((r) => r.data);
export const triggerDistillationTraining = (taskType: string) =>
  api.post(`/admin/distillation/trigger-training/${taskType}`).then((r) => r.data);
export const setDistillationHandoff = (taskType: string, pct: number) =>
  api.post(`/admin/distillation/handoff/${taskType}`, null, { params: { pct } }).then((r) => r.data);

// --- Sessions ---
export const getSessions = () => api.get('/admin/sessions').then((r) => r.data);
export const getSessionDetail = (id: string) => api.get(`/admin/sessions/${id}`).then((r) => r.data);

// --- PII ---
export const getPiiStats = () => api.get('/admin/pii/stats').then((r) => r.data);

// --- OpenClaw ---
export const getOpenClawStatus = () => api.get('/admin/openclaw/status').then((r) => r.data);
export const importOpenClawHistory = (limit = 1000) =>
  api.post('/admin/openclaw/import-history', null, { params: { limit } }).then((r) => r.data);
export const discoverOpenClawModels = () =>
  api.post('/admin/openclaw/discover').then((r) => r.data);

// --- Ollama Management ---
export const getOllamaModels = () => api.get('/admin/ollama/models').then((r) => r.data);

// --- Accounts ---
export const getAccounts = () => api.get('/admin/accounts').then((r) => r.data);

// --- Analytics ---
export const getLocalVsExternal = () => api.get('/admin/analytics/local-vs-external').then((r) => r.data);
export const getLatencyAnalytics = () => api.get('/admin/analytics/latency').then((r) => r.data);

export default api;
