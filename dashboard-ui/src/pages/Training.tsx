import { useEffect, useState } from 'react';
import { Brain, Play, CheckCircle, XCircle, Clock, Loader2 } from 'lucide-react';
import { getTrainingRuns, createTrainingRun } from '../lib/api';

const statusIcons: Record<string, any> = {
  pending: Clock,
  running: Loader2,
  completed: CheckCircle,
  failed: XCircle,
};

const statusColors: Record<string, string> = {
  pending: 'badge-yellow',
  running: 'badge-blue',
  completed: 'badge-green',
  failed: 'badge-red',
};

export default function Training() {
  const [runs, setRuns] = useState<any[]>([]);
  const [creating, setCreating] = useState(false);

  const load = () => {
    getTrainingRuns().then((d) => setRuns(d.data || [])).catch(() => {});
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 10000); // poll for running jobs
    return () => clearInterval(interval);
  }, []);

  const handleCreate = async () => {
    setCreating(true);
    try {
      await createTrainingRun({});
      load();
    } catch {}
    setCreating(false);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Training</h1>
        <button
          onClick={handleCreate}
          disabled={creating}
          className="btn-primary flex items-center gap-2"
        >
          <Play className="w-4 h-4" />
          {creating ? 'Starting...' : 'New Training Run'}
        </button>
      </div>

      {/* Runs */}
      <div className="space-y-4">
        {runs.map((run: any) => {
          const StatusIcon = statusIcons[run.status] || Clock;
          return (
            <div key={run.id} className="card">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <Brain className="w-5 h-5 text-purple-400" />
                  <div>
                    <p className="font-mono text-sm">{run.id.slice(0, 8)}</p>
                    <p className="text-xs text-gray-500">{run.base_model}</p>
                  </div>
                </div>
                <span className={`${statusColors[run.status]} flex items-center gap-1`}>
                  <StatusIcon className={`w-3 h-3 ${run.status === 'running' ? 'animate-spin' : ''}`} />
                  {run.status}
                </span>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4 text-sm">
                <div>
                  <p className="text-gray-500 text-xs">Dataset Size</p>
                  <p>{run.dataset_size} samples</p>
                </div>
                <div>
                  <p className="text-gray-500 text-xs">Config</p>
                  <p className="font-mono text-xs">
                    rank={run.config?.lora_rank} epochs={run.config?.epochs}
                  </p>
                </div>
                <div>
                  <p className="text-gray-500 text-xs">Started</p>
                  <p className="text-xs">{run.started_at ? new Date(run.started_at).toLocaleString() : '—'}</p>
                </div>
                <div>
                  <p className="text-gray-500 text-xs">Completed</p>
                  <p className="text-xs">{run.completed_at ? new Date(run.completed_at).toLocaleString() : '—'}</p>
                </div>
              </div>

              {/* Metrics */}
              {run.metrics && (
                <div className="mt-4 p-3 bg-gray-800/50 rounded-lg">
                  <p className="text-xs text-gray-500 mb-2">Evaluation Results</p>
                  <div className="grid grid-cols-3 gap-4 text-sm">
                    <div>
                      <p className="text-gray-400">Base Loss</p>
                      <p className="font-mono">{run.metrics.avg_base_loss}</p>
                    </div>
                    <div>
                      <p className="text-gray-400">Fine-tuned Loss</p>
                      <p className="font-mono">{run.metrics.avg_finetuned_loss}</p>
                    </div>
                    <div>
                      <p className="text-gray-400">Improvement</p>
                      <p className={`font-mono ${run.metrics.improved ? 'text-emerald-400' : 'text-red-400'}`}>
                        {(run.metrics.improvement * 100).toFixed(1)}%
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {run.ollama_model && (
                <div className="mt-3">
                  <span className="badge-green">Deployed: {run.ollama_model}</span>
                </div>
              )}
            </div>
          );
        })}

        {runs.length === 0 && (
          <div className="card text-center py-12">
            <Brain className="w-12 h-12 text-gray-700 mx-auto mb-3" />
            <p className="text-gray-500">No training runs yet</p>
            <p className="text-xs text-gray-600 mt-1">
              Click "New Training Run" to start fine-tuning a local model
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
