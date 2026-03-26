import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, ThumbsUp, ThumbsDown, Bot, User, Wrench } from 'lucide-react';
import { getConversation, addFeedback } from '../lib/api';

const roleIcon: Record<string, any> = {
  user: User,
  assistant: Bot,
  system: Wrench,
  tool: Wrench,
};

const roleBg: Record<string, string> = {
  user: 'bg-blue-500/10 border-blue-500/20',
  assistant: 'bg-purple-500/10 border-purple-500/20',
  system: 'bg-gray-500/10 border-gray-500/20',
  tool: 'bg-yellow-500/10 border-yellow-500/20',
};

export default function ConversationDetail() {
  const { id } = useParams();
  const [conv, setConv] = useState<any>(null);

  useEffect(() => {
    if (id) getConversation(id).then(setConv).catch(() => {});
  }, [id]);

  if (!conv) {
    return <div className="text-gray-500">Loading...</div>;
  }

  const handleFeedback = async (messageId: string, value: number) => {
    await addFeedback(conv.id, messageId, value);
  };

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center gap-3">
        <Link to="/conversations" className="btn-secondary p-2">
          <ArrowLeft className="w-4 h-4" />
        </Link>
        <div>
          <h1 className="text-xl font-bold">Conversation</h1>
          <p className="text-xs text-gray-500 font-mono">{conv.id}</p>
        </div>
        <span className="badge-purple ml-auto">{conv.source}</span>
      </div>

      {/* Metadata */}
      <div className="card text-sm">
        <div className="grid grid-cols-3 gap-4">
          <div>
            <span className="text-gray-500">User:</span>{' '}
            <span>{conv.user_id || '—'}</span>
          </div>
          <div>
            <span className="text-gray-500">Created:</span>{' '}
            <span>{conv.created_at ? new Date(conv.created_at).toLocaleString() : '—'}</span>
          </div>
          <div>
            <span className="text-gray-500">Messages:</span>{' '}
            <span>{conv.messages?.length ?? 0}</span>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="space-y-3">
        {(conv.messages ?? []).map((msg: any) => {
          const Icon = roleIcon[msg.role] || User;
          return (
            <div
              key={msg.id}
              className={`rounded-xl border p-4 ${roleBg[msg.role] || 'bg-gray-800'}`}
            >
              <div className="flex items-start gap-3">
                <div className="mt-0.5 p-1.5 rounded-lg bg-gray-800">
                  <Icon className="w-4 h-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-medium capitalize text-sm">{msg.role}</span>
                    <span className="text-xs text-gray-500">#{msg.sequence}</span>
                    {msg.token_count && (
                      <span className="text-xs text-gray-600">{msg.token_count} tokens</span>
                    )}
                  </div>
                  <div className="text-sm text-gray-300 whitespace-pre-wrap break-words">
                    {msg.content}
                  </div>

                  {/* Routing decision */}
                  {msg.routing_decision && (
                    <div className="mt-3 p-2 bg-gray-800/50 rounded-lg text-xs space-y-1">
                      <div className="flex flex-wrap gap-2">
                        <span className="badge-blue">{msg.routing_decision.provider}</span>
                        <span className="badge-purple">{msg.routing_decision.model}</span>
                        <span className="badge-yellow">{msg.routing_decision.task_type}</span>
                        <span className="text-gray-500">
                          {msg.routing_decision.latency_ms}ms · ${msg.routing_decision.cost_usd.toFixed(4)} · {msg.routing_decision.prompt_tokens}+{msg.routing_decision.completion_tokens} tokens
                        </span>
                      </div>
                    </div>
                  )}

                  {/* Quality signals */}
                  {msg.quality_signals?.length > 0 && (
                    <div className="mt-2 flex gap-1">
                      {msg.quality_signals.map((s: any, i: number) => (
                        <span
                          key={i}
                          className={s.value >= 0.5 ? 'badge-green' : 'badge-red'}
                        >
                          {s.type}: {s.value}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Feedback buttons for assistant messages */}
                  {msg.role === 'assistant' && (
                    <div className="mt-2 flex gap-2">
                      <button
                        onClick={() => handleFeedback(msg.id, 1.0)}
                        className="p-1 text-gray-500 hover:text-emerald-400 transition-colors"
                        title="Good response"
                      >
                        <ThumbsUp className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => handleFeedback(msg.id, 0.0)}
                        className="p-1 text-gray-500 hover:text-red-400 transition-colors"
                        title="Bad response"
                      >
                        <ThumbsDown className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
