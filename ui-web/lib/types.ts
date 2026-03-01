/* Shared TypeScript types for the router UI. */

// --- Dashboard types ---

export type ClassificationResult = {
  task_type: string;
  complexity: number;
  token_estimate: number;
  requires_tools: boolean;
  factuality_risk: boolean;
};

export type RouteResult = {
  response: string;
  model_used: string;
  task_type: string;
  estimated_cost: number;
  latency_ms: number;
  cache_hit: boolean;
  fallback_triggered: boolean;
  confidence: number | null;
};

export type ProviderStatus = {
  name: string;
  display_name: string;
  category: string;
  model_id: string;
  enabled: boolean;
  healthy: boolean;
  input_price: number;
  output_price: number;
  cached_input_price: number;
};

export type ProviderPayload = {
  default_model: string;
  providers: ProviderStatus[];
};

export type CostSummary = {
  total_cost: number;
  request_count: number;
  baseline_cost: number;
  savings_percentage: number;
  cache_hit_rate: number;
  cost_by_model: Record<string, number>;
};

export type CalibrationResult = {
  run_id: string;
  timestamp: string;
  prompts_count: number;
  models_tested: string[];
  win_rate_by_task: Record<string, { classification_accuracy: number }>;
  avg_latency_by_model: Record<string, number>;
  total_cost_by_model: Record<string, number>;
  regret_rate: number;
  cost_vs_baseline: number;
};

export type RequestEntry = {
  id: string;
  timestamp: string;
  model_used: string;
  task_type: string;
  input_tokens: number;
  output_tokens: number;
  cost: number;
  latency_ms: number;
  cache_hit: boolean;
  fallback_triggered: boolean;
};

export type TimelinePayload = {
  total: number;
  items: RequestEntry[];
};

// --- Chat types ---

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  model_used?: string;
  task_type?: string;
  estimated_cost?: number;
  latency_ms?: number;
  cache_hit?: boolean;
  fallback_triggered?: boolean;
  confidence?: number | null;
};

export type Conversation = {
  id: string;
  title: string;
  messages: Message[];
  created_at: string;
};
