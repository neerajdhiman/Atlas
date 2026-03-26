import { useEffect, useState } from 'react';
import { Settings as SettingsIcon, Key, GitBranch, Brain, Save } from 'lucide-react';

export default function SettingsPage() {
  const [config, setConfig] = useState({
    anthropic_api_key: '',
    openai_api_key: '',
    vertex_project_id: '',
    ollama_base_url: 'http://localhost:11434',
    default_strategy: 'best_quality',
    exploration_rate: 0.1,
    training_base_model: 'mistralai/Mistral-7B-Instruct-v0.3',
    training_lora_rank: 16,
    training_min_quality: 0.7,
    training_min_samples: 500,
  });

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-2xl font-bold">Settings</h1>

      {/* Provider API Keys */}
      <div className="card">
        <div className="flex items-center gap-2 mb-4">
          <Key className="w-5 h-5 text-yellow-400" />
          <h2 className="font-medium">Provider API Keys</h2>
        </div>
        <p className="text-sm text-gray-400 mb-4">
          Configure via environment variables (A1_ANTHROPIC_API_KEY, etc.) or .env file.
        </p>
        <div className="space-y-3">
          <div>
            <label className="text-sm text-gray-400 block mb-1">Anthropic API Key</label>
            <input
              type="password"
              value={config.anthropic_api_key}
              onChange={(e) => setConfig({ ...config, anthropic_api_key: e.target.value })}
              placeholder="sk-ant-..."
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-blue-500"
            />
          </div>
          <div>
            <label className="text-sm text-gray-400 block mb-1">OpenAI API Key</label>
            <input
              type="password"
              value={config.openai_api_key}
              onChange={(e) => setConfig({ ...config, openai_api_key: e.target.value })}
              placeholder="sk-..."
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-blue-500"
            />
          </div>
          <div>
            <label className="text-sm text-gray-400 block mb-1">Google Vertex Project ID</label>
            <input
              type="text"
              value={config.vertex_project_id}
              onChange={(e) => setConfig({ ...config, vertex_project_id: e.target.value })}
              placeholder="my-gcp-project"
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-blue-500"
            />
          </div>
          <div>
            <label className="text-sm text-gray-400 block mb-1">Ollama Base URL</label>
            <input
              type="text"
              value={config.ollama_base_url}
              onChange={(e) => setConfig({ ...config, ollama_base_url: e.target.value })}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-blue-500"
            />
          </div>
        </div>
      </div>

      {/* Routing Policy */}
      <div className="card">
        <div className="flex items-center gap-2 mb-4">
          <GitBranch className="w-5 h-5 text-blue-400" />
          <h2 className="font-medium">Routing Policy</h2>
        </div>
        <div className="space-y-3">
          <div>
            <label className="text-sm text-gray-400 block mb-1">Default Strategy</label>
            <select
              value={config.default_strategy}
              onChange={(e) => setConfig({ ...config, default_strategy: e.target.value })}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-blue-500"
            >
              <option value="best_quality">Best Quality</option>
              <option value="lowest_cost">Lowest Cost</option>
              <option value="lowest_latency">Lowest Latency</option>
            </select>
          </div>
          <div>
            <label className="text-sm text-gray-400 block mb-1">
              Exploration Rate ({(config.exploration_rate * 100).toFixed(0)}%)
            </label>
            <input
              type="range"
              min="0"
              max="0.5"
              step="0.05"
              value={config.exploration_rate}
              onChange={(e) => setConfig({ ...config, exploration_rate: parseFloat(e.target.value) })}
              className="w-full"
            />
            <p className="text-xs text-gray-600 mt-1">
              Percentage of requests randomly routed to non-optimal models for data collection
            </p>
          </div>
        </div>
      </div>

      {/* Training Config */}
      <div className="card">
        <div className="flex items-center gap-2 mb-4">
          <Brain className="w-5 h-5 text-purple-400" />
          <h2 className="font-medium">Training Configuration</h2>
        </div>
        <div className="space-y-3">
          <div>
            <label className="text-sm text-gray-400 block mb-1">Base Model</label>
            <input
              type="text"
              value={config.training_base_model}
              onChange={(e) => setConfig({ ...config, training_base_model: e.target.value })}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm font-mono focus:outline-none focus:border-blue-500"
            />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-sm text-gray-400 block mb-1">LoRA Rank</label>
              <input
                type="number"
                value={config.training_lora_rank}
                onChange={(e) => setConfig({ ...config, training_lora_rank: parseInt(e.target.value) })}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="text-sm text-gray-400 block mb-1">Min Quality</label>
              <input
                type="number"
                step="0.1"
                value={config.training_min_quality}
                onChange={(e) => setConfig({ ...config, training_min_quality: parseFloat(e.target.value) })}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="text-sm text-gray-400 block mb-1">Min Samples</label>
              <input
                type="number"
                value={config.training_min_samples}
                onChange={(e) => setConfig({ ...config, training_min_samples: parseInt(e.target.value) })}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>
        </div>
      </div>

      <div className="text-sm text-gray-600">
        Note: Settings are configured via environment variables or config files.
        Changes made here are for display only. Edit config/settings.py or set
        A1_* environment variables to persist changes.
      </div>
    </div>
  );
}
