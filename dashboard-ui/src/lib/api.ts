import axios from 'axios';
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

// Response interceptor: handle auth errors
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().logout();
    }
    // Let pages handle their own error display
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

export default api;
