import { useState } from 'react';
import { Download, Upload, CheckCircle, AlertCircle } from 'lucide-react';
import { triggerPaperclipImport } from '../lib/api';

export default function Import() {
  const [apiUrl, setApiUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState('');

  const handleImport = async () => {
    if (!apiUrl) return;
    setImporting(true);
    setError('');
    setResult(null);
    try {
      const stats = await triggerPaperclipImport(apiUrl, apiKey || undefined);
      setResult(stats);
    } catch (e: any) {
      setError(e.message || 'Import failed');
    }
    setImporting(false);
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-2xl font-bold">Import</h1>

      {/* Paperclip.ing import */}
      <div className="card">
        <div className="flex items-center gap-2 mb-4">
          <Download className="w-5 h-5 text-blue-400" />
          <h2 className="font-medium">Import from Paperclip.ing</h2>
        </div>
        <p className="text-sm text-gray-400 mb-4">
          Import conversation history from your paperclip.ing instance.
          Conversations will be normalized and stored for training data.
        </p>
        <div className="space-y-3">
          <div>
            <label className="text-sm text-gray-400 block mb-1">API URL</label>
            <input
              type="text"
              value={apiUrl}
              onChange={(e) => setApiUrl(e.target.value)}
              placeholder="https://your-instance.paperclip.ing"
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-blue-500"
            />
          </div>
          <div>
            <label className="text-sm text-gray-400 block mb-1">API Key (optional)</label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-..."
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-blue-500"
            />
          </div>
          <button
            onClick={handleImport}
            disabled={importing || !apiUrl}
            className="btn-primary flex items-center gap-2 disabled:opacity-50"
          >
            <Upload className="w-4 h-4" />
            {importing ? 'Importing...' : 'Start Import'}
          </button>
        </div>

        {result && (
          <div className="mt-4 p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <CheckCircle className="w-4 h-4 text-emerald-400" />
              <span className="font-medium text-emerald-400">Import Complete</span>
            </div>
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div>
                <p className="text-gray-400">Imported</p>
                <p className="font-bold text-emerald-400">{result.imported}</p>
              </div>
              <div>
                <p className="text-gray-400">Skipped (dupes)</p>
                <p>{result.skipped}</p>
              </div>
              <div>
                <p className="text-gray-400">Errors</p>
                <p className={result.errors > 0 ? 'text-red-400' : ''}>{result.errors}</p>
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="mt-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-red-400" />
            <span className="text-red-400 text-sm">{error}</span>
          </div>
        )}
      </div>

      {/* JSONL import */}
      <div className="card">
        <div className="flex items-center gap-2 mb-4">
          <Download className="w-5 h-5 text-purple-400" />
          <h2 className="font-medium">Import from JSONL</h2>
        </div>
        <p className="text-sm text-gray-400 mb-4">
          Import conversations from an OpenAI-style JSONL file. Each line should be:
        </p>
        <pre className="text-xs bg-gray-800 p-3 rounded-lg font-mono text-gray-400 mb-4">
          {`{"messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}`}
        </pre>
        <p className="text-xs text-gray-500">
          Use the API endpoint directly: POST /admin/import/jsonl?file_path=/path/to/file.jsonl
        </p>
      </div>
    </div>
  );
}
