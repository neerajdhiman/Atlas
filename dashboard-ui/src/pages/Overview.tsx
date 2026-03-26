import { useEffect, useState } from 'react';
import {
  Activity,
  Zap,
  DollarSign,
  Clock,
  AlertCircle,
  MessageSquare,
  Server,
} from 'lucide-react';
import { getOverview, connectLiveFeed } from '../lib/api';
import LiveFeed from '../components/LiveFeed';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';

const COLORS = ['#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#ec4899'];

export default function Overview() {
  const [data, setData] = useState<any>(null);
  const [liveEvents, setLiveEvents] = useState<any[]>([]);

  useEffect(() => {
    getOverview().then(setData).catch(() => {});
    const interval = setInterval(() => {
      getOverview().then(setData).catch(() => {});
    }, 5000);

    const ws = connectLiveFeed((event) => {
      setLiveEvents((prev) => [event, ...prev].slice(0, 50));
    });

    return () => {
      clearInterval(interval);
      ws.close();
    };
  }, []);

  const m = data?.metrics;

  const providerData = m?.provider_counts
    ? Object.entries(m.provider_counts).map(([name, count]) => ({
        name,
        value: count as number,
      }))
    : [];

  const taskData = m?.task_type_counts
    ? Object.entries(m.task_type_counts).map(([name, count]) => ({
        name,
        value: count as number,
      }))
    : [];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Overview</h1>

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
        <div className="stat-card">
          <div className="flex items-center gap-2 text-gray-400">
            <Zap className="w-4 h-4" />
            <span className="stat-label">Requests</span>
          </div>
          <span className="stat-value">{m?.request_count ?? '—'}</span>
        </div>
        <div className="stat-card">
          <div className="flex items-center gap-2 text-gray-400">
            <Activity className="w-4 h-4" />
            <span className="stat-label">Req/min</span>
          </div>
          <span className="stat-value">{m?.requests_per_minute ?? '—'}</span>
        </div>
        <div className="stat-card">
          <div className="flex items-center gap-2 text-gray-400">
            <Clock className="w-4 h-4" />
            <span className="stat-label">Avg Latency</span>
          </div>
          <span className="stat-value">{m?.avg_latency_ms ?? '—'}ms</span>
        </div>
        <div className="stat-card">
          <div className="flex items-center gap-2 text-gray-400">
            <DollarSign className="w-4 h-4" />
            <span className="stat-label">Total Cost</span>
          </div>
          <span className="stat-value">${m?.total_cost_usd ?? '0'}</span>
        </div>
        <div className="stat-card">
          <div className="flex items-center gap-2 text-gray-400">
            <AlertCircle className="w-4 h-4" />
            <span className="stat-label">Errors</span>
          </div>
          <span className="stat-value text-red-400">{m?.error_count ?? 0}</span>
        </div>
        <div className="stat-card">
          <div className="flex items-center gap-2 text-gray-400">
            <MessageSquare className="w-4 h-4" />
            <span className="stat-label">Conversations</span>
          </div>
          <span className="stat-value">{data?.conversations_count ?? '—'}</span>
        </div>
        <div className="stat-card">
          <div className="flex items-center gap-2 text-gray-400">
            <Server className="w-4 h-4" />
            <span className="stat-label">Providers</span>
          </div>
          <span className="stat-value">
            {data?.providers?.filter((p: any) => p.healthy).length ?? 0}/
            {data?.providers?.length ?? 0}
          </span>
        </div>
      </div>

      {/* Charts + Live Feed */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Provider distribution */}
        <div className="card">
          <h2 className="text-sm font-medium text-gray-400 mb-3">Provider Distribution</h2>
          {providerData.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie data={providerData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={75}>
                  {providerData.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[200px] flex items-center justify-center text-gray-600">
              No data yet
            </div>
          )}
          <div className="flex flex-wrap gap-2 mt-2">
            {providerData.map((d, i) => (
              <span key={d.name} className="text-xs flex items-center gap-1">
                <span className="w-2 h-2 rounded-full" style={{ background: COLORS[i % COLORS.length] }} />
                {d.name}: {d.value}
              </span>
            ))}
          </div>
        </div>

        {/* Task type distribution */}
        <div className="card">
          <h2 className="text-sm font-medium text-gray-400 mb-3">Task Types</h2>
          {taskData.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie data={taskData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={75}>
                  {taskData.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[200px] flex items-center justify-center text-gray-600">
              No data yet
            </div>
          )}
          <div className="flex flex-wrap gap-2 mt-2">
            {taskData.map((d, i) => (
              <span key={d.name} className="text-xs flex items-center gap-1">
                <span className="w-2 h-2 rounded-full" style={{ background: COLORS[i % COLORS.length] }} />
                {d.name}: {d.value}
              </span>
            ))}
          </div>
        </div>

        {/* Live Feed */}
        <div className="card">
          <h2 className="text-sm font-medium text-gray-400 mb-3">
            Live Feed
            <span className="ml-2 inline-flex h-2 w-2 rounded-full bg-green-500 animate-pulse" />
          </h2>
          <LiveFeed events={liveEvents} />
        </div>
      </div>

      {/* Provider health */}
      <div className="card">
        <h2 className="text-sm font-medium text-gray-400 mb-3">Provider Health</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {(data?.providers ?? []).map((p: any) => (
            <div
              key={p.name}
              className={`p-3 rounded-lg border ${
                p.healthy ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-red-500/30 bg-red-500/5'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-medium capitalize">{p.name}</span>
                <span className={p.healthy ? 'badge-green' : 'badge-red'}>
                  {p.healthy ? 'Healthy' : 'Down'}
                </span>
              </div>
              <p className="text-xs text-gray-500 mt-1">
                {p.models?.length ?? 0} models
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
