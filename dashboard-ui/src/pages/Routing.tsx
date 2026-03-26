import { useEffect, useState } from 'react';
import { GitBranch, Trophy } from 'lucide-react';
import { getRoutingDecisions, getRoutingPerformance } from '../lib/api';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

export default function Routing() {
  const [decisions, setDecisions] = useState<any[]>([]);
  const [performance, setPerformance] = useState<any[]>([]);

  useEffect(() => {
    getRoutingDecisions(50).then((d) => setDecisions(d.data || [])).catch(() => {});
    getRoutingPerformance().then((d) => setPerformance(d.data || [])).catch(() => {});
  }, []);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Routing</h1>

      {/* Model Leaderboard */}
      <div className="card">
        <div className="flex items-center gap-2 mb-4">
          <Trophy className="w-4 h-4 text-yellow-500" />
          <h2 className="font-medium">Model Leaderboard</h2>
        </div>
        {performance.length > 0 ? (
          <>
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={performance}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="model" tick={{ fontSize: 11, fill: '#9ca3af' }} />
                <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} />
                <Tooltip contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }} />
                <Bar dataKey="avg_quality" fill="#3b82f6" name="Quality" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
            <table className="w-full text-sm mt-4">
              <thead>
                <tr className="text-gray-500 text-xs">
                  <th className="text-left p-2">Model</th>
                  <th className="text-left p-2">Task</th>
                  <th className="text-right p-2">Quality</th>
                  <th className="text-right p-2">Latency</th>
                  <th className="text-right p-2">Cost</th>
                  <th className="text-right p-2">Samples</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {performance.map((p: any, i: number) => (
                  <tr key={i}>
                    <td className="p-2 font-mono text-xs">{p.model}</td>
                    <td className="p-2"><span className="badge-yellow">{p.task_type}</span></td>
                    <td className="p-2 text-right">{p.avg_quality?.toFixed(2)}</td>
                    <td className="p-2 text-right text-gray-400">{p.avg_latency_ms?.toFixed(0)}ms</td>
                    <td className="p-2 text-right text-gray-400">${p.avg_cost_usd?.toFixed(4)}</td>
                    <td className="p-2 text-right text-gray-500">{p.sample_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : (
          <div className="text-center text-gray-600 py-8">
            No performance data yet. Route some requests first.
          </div>
        )}
      </div>

      {/* Recent Decisions */}
      <div className="card">
        <div className="flex items-center gap-2 mb-4">
          <GitBranch className="w-4 h-4 text-blue-500" />
          <h2 className="font-medium">Recent Routing Decisions</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-500 text-xs">
                <th className="text-left p-2">Time</th>
                <th className="text-left p-2">Provider</th>
                <th className="text-left p-2">Model</th>
                <th className="text-left p-2">Task</th>
                <th className="text-left p-2">Strategy</th>
                <th className="text-right p-2">Latency</th>
                <th className="text-right p-2">Cost</th>
                <th className="text-right p-2">Tokens</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {decisions.map((d: any) => (
                <tr key={d.id} className="hover:bg-gray-800/30">
                  <td className="p-2 text-xs text-gray-500">
                    {d.created_at ? new Date(d.created_at).toLocaleTimeString() : '—'}
                  </td>
                  <td className="p-2"><span className="badge-blue">{d.provider}</span></td>
                  <td className="p-2 font-mono text-xs">{d.model}</td>
                  <td className="p-2"><span className="badge-yellow">{d.task_type || '—'}</span></td>
                  <td className="p-2 text-gray-400 text-xs">{d.strategy}</td>
                  <td className="p-2 text-right">{d.latency_ms}ms</td>
                  <td className="p-2 text-right">${d.cost_usd?.toFixed(4)}</td>
                  <td className="p-2 text-right text-gray-400">
                    {d.prompt_tokens}+{d.completion_tokens}
                  </td>
                </tr>
              ))}
              {decisions.length === 0 && (
                <tr>
                  <td colSpan={8} className="p-8 text-center text-gray-600">
                    No routing decisions yet
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
