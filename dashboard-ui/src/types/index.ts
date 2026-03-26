export interface Conversation {
  id: string;
  source: string;
  user_id: string | null;
  message_count: number;
  created_at: string | null;
  metadata: Record<string, any>;
}

export interface Message {
  id: string;
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string;
  tool_calls: any | null;
  token_count: number | null;
  sequence: number;
  created_at: string | null;
  routing_decision: RoutingDecision | null;
  quality_signals: QualitySignal[];
}

export interface RoutingDecision {
  id: string;
  provider: string;
  model: string;
  task_type: string | null;
  strategy: string;
  confidence: number | null;
  latency_ms: number;
  cost_usd: number;
  prompt_tokens: number;
  completion_tokens: number;
  error: string | null;
  created_at: string | null;
}

export interface QualitySignal {
  type: string;
  value: number;
  evaluator: string | null;
}

export interface Provider {
  name: string;
  healthy: boolean;
  models: string[];
}

export interface ModelInfo {
  id: string;
  object: string;
  owned_by: string;
  context_window: number;
}

export interface TrainingRun {
  id: string;
  base_model: string;
  dataset_size: number;
  status: 'pending' | 'running' | 'completed' | 'failed';
  config: Record<string, any>;
  metrics: Record<string, any> | null;
  ollama_model: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string | null;
}

export interface ModelPerformance {
  task_type: string;
  provider: string;
  model: string;
  avg_quality: number;
  avg_latency_ms: number;
  avg_cost_usd: number;
  sample_count: number;
}

export interface MetricsSnapshot {
  uptime_seconds: number;
  request_count: number;
  error_count: number;
  avg_latency_ms: number;
  total_cost_usd: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  requests_per_minute: number;
  provider_counts: Record<string, number>;
  model_counts: Record<string, number>;
  task_type_counts: Record<string, number>;
}

export interface OverviewData {
  metrics: MetricsSnapshot;
  conversations_count: number;
  providers: Provider[];
  active_connections: number;
}

export interface Notification {
  id: string;
  type: 'info' | 'success' | 'warning' | 'error';
  title: string;
  message: string;
  timestamp: number;
  read: boolean;
}
