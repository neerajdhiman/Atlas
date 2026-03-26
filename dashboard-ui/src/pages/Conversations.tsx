import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { MessageSquare, Search, ChevronLeft, ChevronRight } from 'lucide-react';
import { getConversations } from '../lib/api';

export default function Conversations() {
  const [data, setData] = useState<any>(null);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState('');
  const limit = 25;

  useEffect(() => {
    getConversations(limit, offset).then(setData).catch(() => {});
  }, [offset]);

  const conversations = data?.data ?? [];
  const total = data?.total ?? 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Conversations</h1>
        <span className="text-sm text-gray-500">{total} total</span>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
        <input
          type="text"
          placeholder="Search conversations..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-10 pr-4 py-2.5 bg-gray-900 border border-gray-800 rounded-lg text-sm focus:outline-none focus:border-blue-500"
        />
      </div>

      {/* Table */}
      <div className="card overflow-hidden p-0">
        <table className="w-full text-sm">
          <thead className="bg-gray-800/50">
            <tr>
              <th className="text-left p-3 text-gray-400 font-medium">ID</th>
              <th className="text-left p-3 text-gray-400 font-medium">Source</th>
              <th className="text-left p-3 text-gray-400 font-medium">User</th>
              <th className="text-left p-3 text-gray-400 font-medium">Messages</th>
              <th className="text-left p-3 text-gray-400 font-medium">Created</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {conversations.map((c: any) => (
              <tr key={c.id} className="hover:bg-gray-800/30 transition-colors">
                <td className="p-3">
                  <Link
                    to={`/conversations/${c.id}`}
                    className="text-blue-400 hover:text-blue-300 font-mono text-xs"
                  >
                    {c.id.slice(0, 8)}...
                  </Link>
                </td>
                <td className="p-3">
                  <span className="badge-purple">{c.source}</span>
                </td>
                <td className="p-3 text-gray-400">{c.user_id || '—'}</td>
                <td className="p-3">
                  <span className="flex items-center gap-1 text-gray-400">
                    <MessageSquare className="w-3 h-3" />
                    {c.message_count}
                  </span>
                </td>
                <td className="p-3 text-gray-500 text-xs">
                  {c.created_at ? new Date(c.created_at).toLocaleString() : '—'}
                </td>
              </tr>
            ))}
            {conversations.length === 0 && (
              <tr>
                <td colSpan={5} className="p-8 text-center text-gray-600">
                  No conversations yet
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between">
        <span className="text-sm text-gray-500">
          Showing {offset + 1}–{Math.min(offset + limit, total)} of {total}
        </span>
        <div className="flex gap-2">
          <button
            onClick={() => setOffset(Math.max(0, offset - limit))}
            disabled={offset === 0}
            className="btn-secondary disabled:opacity-50"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <button
            onClick={() => setOffset(offset + limit)}
            disabled={offset + limit >= total}
            className="btn-secondary disabled:opacity-50"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
