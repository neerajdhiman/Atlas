interface LiveFeedProps {
  events: any[];
}

export default function LiveFeed({ events }: LiveFeedProps) {
  if (events.length === 0) {
    return (
      <div className="h-[200px] flex items-center justify-center text-gray-600 text-sm">
        Waiting for requests...
      </div>
    );
  }

  return (
    <div className="h-[200px] overflow-y-auto space-y-1 text-xs font-mono">
      {events.map((e, i) => (
        <div
          key={i}
          className="flex items-center gap-2 py-1 px-2 rounded bg-gray-800/50 animate-fade-in"
        >
          <span className="text-gray-500">{new Date(e.timestamp || Date.now()).toLocaleTimeString()}</span>
          <span className={`badge-${e.error ? 'red' : 'blue'}`}>
            {e.provider || 'unknown'}
          </span>
          <span className="text-gray-400 truncate">{e.model || '—'}</span>
          <span className="text-gray-600 ml-auto">{e.latency_ms || '—'}ms</span>
        </div>
      ))}
    </div>
  );
}
