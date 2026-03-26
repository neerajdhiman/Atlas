import { useEffect, useState } from 'react';
import { Server, RefreshCw, CheckCircle, XCircle } from 'lucide-react';
import { getProviders, refreshProviders, getModels } from '../lib/api';

export default function Providers() {
  const [providers, setProviders] = useState<any[]>([]);
  const [models, setModels] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = () => {
    getProviders().then((d) => setProviders(d.data || [])).catch(() => {});
    getModels().then((d) => setModels(d.data || [])).catch(() => {});
  };

  useEffect(load, []);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      const result = await refreshProviders();
      setProviders(result.providers || []);
    } catch {}
    setRefreshing(false);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Providers</h1>
        <button onClick={handleRefresh} className="btn-secondary flex items-center gap-2">
          <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
          Refresh Health
        </button>
      </div>

      {/* Provider cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {providers.map((p: any) => (
          <div key={p.name} className="card">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Server className="w-5 h-5 text-gray-400" />
                <h3 className="font-bold text-lg capitalize">{p.name}</h3>
              </div>
              {p.healthy ? (
                <span className="badge-green flex items-center gap-1">
                  <CheckCircle className="w-3 h-3" /> Healthy
                </span>
              ) : (
                <span className="badge-red flex items-center gap-1">
                  <XCircle className="w-3 h-3" /> Unavailable
                </span>
              )}
            </div>
            <div className="space-y-2">
              <p className="text-sm text-gray-400">
                {p.models?.length ?? 0} models available
              </p>
              <div className="flex flex-wrap gap-1">
                {(p.models || []).map((m: string) => (
                  <span key={m} className="badge-blue font-mono text-xs">
                    {m}
                  </span>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* All available models */}
      <div className="card">
        <h2 className="font-medium mb-4">All Available Models</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-500 text-xs">
                <th className="text-left p-2">Model ID</th>
                <th className="text-left p-2">Provider</th>
                <th className="text-right p-2">Context Window</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {models.map((m: any) => (
                <tr key={m.id}>
                  <td className="p-2 font-mono text-xs">{m.id}</td>
                  <td className="p-2"><span className="badge-purple">{m.owned_by}</span></td>
                  <td className="p-2 text-right text-gray-400">
                    {m.context_window?.toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
