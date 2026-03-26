import { useEffect, useState } from 'react';
import { Typography, Card, Table, Tag, Space, Select, Row, Col } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { getRoutingDecisions, getRoutingPerformance } from '../lib/api';
import ExportDropdown from '../components/shared/ExportDropdown';
import DateRangeFilter from '../components/shared/DateRangeFilter';
import PageSkeleton from '../components/shared/PageSkeleton';
import dayjs from 'dayjs';

export default function Routing() {
  const [decisions, setDecisions] = useState<any[]>([]);
  const [performance, setPerformance] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [taskFilter, setTaskFilter] = useState<string | undefined>();
  const [dateRange, setDateRange] = useState<[string | null, string | null]>([null, null]);

  useEffect(() => {
    Promise.all([
      getRoutingDecisions({ limit: 100, date_from: dateRange[0] || undefined, date_to: dateRange[1] || undefined }),
      getRoutingPerformance(taskFilter),
    ])
      .then(([d, p]) => { setDecisions(d.data || []); setPerformance(p.data || []); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [taskFilter, dateRange]);

  if (loading) return <PageSkeleton type="table" />;

  const columns: ColumnsType<any> = [
    { title: 'Time', dataIndex: 'created_at', width: 100, render: (d: string) => d ? dayjs(d).format('HH:mm:ss') : '—' },
    { title: 'Provider', dataIndex: 'provider', width: 110, render: (p: string) => <Tag color="blue">{p}</Tag>, filters: [...new Set(decisions.map((d) => d.provider))].map((p) => ({ text: p, value: p })), onFilter: (v, r) => r.provider === v },
    { title: 'Model', dataIndex: 'model', width: 200, ellipsis: true, render: (m: string) => <span style={{ fontFamily: 'monospace', fontSize: 11 }}>{m}</span> },
    { title: 'Task', dataIndex: 'task_type', width: 120, render: (t: string) => <Tag color="gold">{t || '—'}</Tag> },
    { title: 'Strategy', dataIndex: 'strategy', width: 110 },
    { title: 'Latency', dataIndex: 'latency_ms', width: 90, sorter: (a: any, b: any) => a.latency_ms - b.latency_ms, render: (v: number) => `${v}ms` },
    { title: 'Cost', dataIndex: 'cost_usd', width: 90, sorter: (a: any, b: any) => a.cost_usd - b.cost_usd, render: (v: number) => `$${v?.toFixed(4)}` },
    { title: 'Tokens', key: 'tokens', width: 120, render: (_: any, r: any) => `${r.prompt_tokens}+${r.completion_tokens}` },
  ];

  return (
    <div>
      <Typography.Title level={4}>Routing</Typography.Title>

      {/* Leaderboard */}
      <Card title="Model Leaderboard" size="small" style={{ marginBottom: 16 }}
        extra={<Select placeholder="Filter task type" allowClear onChange={setTaskFilter} style={{ width: 160 }}
          options={[...new Set(performance.map((p) => p.task_type))].map((t) => ({ value: t, label: t }))} />}
      >
        {performance.length > 0 ? (
          <>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={performance}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="model" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="avg_quality" fill="#3b82f6" name="Quality" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
            <Table columns={[
              { title: 'Model', dataIndex: 'model', render: (m: string) => <span style={{ fontFamily: 'monospace', fontSize: 11 }}>{m}</span> },
              { title: 'Task', dataIndex: 'task_type', render: (t: string) => <Tag color="gold">{t}</Tag> },
              { title: 'Quality', dataIndex: 'avg_quality', sorter: (a: any, b: any) => a.avg_quality - b.avg_quality, render: (v: number) => v?.toFixed(2) },
              { title: 'Latency', dataIndex: 'avg_latency_ms', sorter: (a: any, b: any) => a.avg_latency_ms - b.avg_latency_ms, render: (v: number) => `${v?.toFixed(0)}ms` },
              { title: 'Cost', dataIndex: 'avg_cost_usd', sorter: (a: any, b: any) => a.avg_cost_usd - b.avg_cost_usd, render: (v: number) => `$${v?.toFixed(4)}` },
              { title: 'Samples', dataIndex: 'sample_count' },
            ]} dataSource={performance} rowKey={(r) => `${r.model}-${r.task_type}`} size="small" pagination={false} style={{ marginTop: 16 }} />
          </>
        ) : (
          <div style={{ textAlign: 'center', padding: 40, color: '#6b7280' }}>No performance data yet</div>
        )}
      </Card>

      {/* Decisions */}
      <Card title="Recent Routing Decisions" size="small"
        extra={<Space><DateRangeFilter value={dateRange} onChange={setDateRange} /><ExportDropdown data={decisions} filename="routing-decisions" /></Space>}
      >
        <Table columns={columns} dataSource={decisions} rowKey="id" size="small"
          pagination={{ pageSize: 25, showSizeChanger: true, showTotal: (t) => `${t} decisions` }}
          scroll={{ x: 900 }} />
      </Card>
    </div>
  );
}
