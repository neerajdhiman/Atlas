import { useEffect, useState } from 'react';
import { BarChart3, TrendingUp } from 'lucide-react';
import { getMetrics, getRoutingDecisions } from '../lib/api';
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts';

const COLORS = ['#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#ec4899'];

export default function Analytics() {
  const [metrics, setMetrics] = useState<any>(null);
  const [decisions, setDecisions] = useState<any[]>([]);

  useEffect(() => {
    getMetrics().then(setMetrics).catch(() => {});
    getRoutingDecisions(200).then((d) => setDecisions(d.data || [])).catch(() => {});
  }, []);

  // Aggregate cost by provider
  const costByProvider: Record<string, number> = {};
  const latencyByModel: Record<string, { total: number; count: number }> = {};
  const tokensByModel: Record<string, number> = {};

  for (const d of decisions) {
    costByProvider[d.provider] = (costByProvider[d.provider] || 0) + (d.cost_usd || 0);
    if (!latencyByModel[d.model]) latencyByModel[d.model] = { total: 0, count: 0 };
    latencyByModel[d.model].total += d.latency_ms || 0;
    latencyByModel[d.model].count += 1;
    tokensByModel[d.model] = (tokensByModel[d.model] || 0) + (d.prompt_tokens || 0) + (d.completion_tokens || 0);
  }

  const costData = Object.entries(costByProvider).map(([name, cost]) => ({
    name,
    cost: parseFloat(cost.toFixed(4)),
  }));

  const latencyData = Object.entries(latencyByModel).map(([name, { total, count }]) => ({
    name: name.length > 20 ? name.slice(0, 20) + '...' : name,
    avg_latency: Math.round(total / count),
  }));

  const tokenData = Object.entries(tokensByModel).map(([name, tokens]) => ({
    name: name.length > 20 ? name.slice(0, 20) + '...' : name,
    tokens,
  }));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Analytics</h1>

      {/* Summary stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="stat-card">
          <span className="stat-label">Total Requests</span>
          <span className="stat-value">{metrics?.request_count ?? 0}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Total Cost</span>
          <span className="stat-value">${metrics?.total_cost_usd ?? '0.00'}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Total Tokens</span>
          <span className="stat-value">
            {((metrics?.total_prompt_tokens ?? 0) + (metrics?.total_completion_tokens ?? 0)).toLocaleString()}
          </span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Uptime</span>
          <span className="stat-value">
            {metrics?.uptime_seconds ? `${Math.round(metrics.uptime_seconds / 60)}m` : '—'}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Cost by provider */}
        <div className="card">
          <h2 className="text-sm font-medium text-gray-400 mb-3">Cost by Provider</h2>
          {costData.length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={costData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#9ca3af' }} />
                <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} />
                <Tooltip contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }} />
                <Bar dataKey="cost" fill="#10b981" name="Cost ($)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[250px] flex items-center justify-center text-gray-600">No data</div>
          )}
        </div>

        {/* Latency by model */}
        <div className="card">
          <h2 className="text-sm font-medium text-gray-400 mb-3">Avg Latency by Model</h2>
          {latencyData.length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={latencyData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#9ca3af' }} />
                <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} />
                <Tooltip contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }} />
                <Bar dataKey="avg_latency" fill="#f59e0b" name="Latency (ms)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[250px] flex items-center justify-center text-gray-600">No data</div>
          )}
        </div>

        {/* Token usage */}
        <div className="card">
          <h2 className="text-sm font-medium text-gray-400 mb-3">Token Usage by Model</h2>
          {tokenData.length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <PieChart>
                <Pie data={tokenData} dataKey="tokens" nameKey="name" cx="50%" cy="50%" outerRadius={90}>
                  {tokenData.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[250px] flex items-center justify-center text-gray-600">No data</div>
          )}
          <div className="flex flex-wrap gap-2 mt-2">
            {tokenData.map((d, i) => (
              <span key={d.name} className="text-xs flex items-center gap-1">
                <span className="w-2 h-2 rounded-full" style={{ background: COLORS[i % COLORS.length] }} />
                {d.name}: {d.tokens.toLocaleString()}
              </span>
            ))}
          </div>
        </div>

        {/* Task distribution */}
        <div className="card">
          <h2 className="text-sm font-medium text-gray-400 mb-3">Task Type Distribution</h2>
          {metrics?.task_type_counts && Object.keys(metrics.task_type_counts).length > 0 ? (
            <>
              <ResponsiveContainer width="100%" height={250}>
                <BarChart
                  data={Object.entries(metrics.task_type_counts).map(([name, count]) => ({
                    name,
                    count,
                  }))}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#9ca3af' }} />
                  <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} />
                  <Tooltip contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }} />
                  <Bar dataKey="count" fill="#8b5cf6" name="Requests" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </>
          ) : (
            <div className="h-[250px] flex items-center justify-center text-gray-600">No data</div>
          )}
        </div>
      </div>
    </div>
  );
}
