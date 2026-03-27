import { useEffect, useState } from 'react';
import { Typography, Card, Table, Tag, Space, Select, Row, Col, Statistic, Button } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  BranchesOutlined, ClockCircleOutlined, ThunderboltOutlined, DollarOutlined,
  CheckCircleOutlined, ReloadOutlined, RocketOutlined,
} from '@ant-design/icons';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { getRoutingDecisions, getRoutingPerformance, getModelLeaderboard, getRecentRequests } from '../lib/api';
import ExportDropdown from '../components/shared/ExportDropdown';
import DateRangeFilter from '../components/shared/DateRangeFilter';
import PageSkeleton from '../components/shared/PageSkeleton';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
dayjs.extend(relativeTime);

export default function Routing() {
  const [decisions, setDecisions] = useState<any[]>([]);
  const [performance, setPerformance] = useState<any[]>([]);
  const [leaderboard, setLeaderboard] = useState<any[]>([]);
  const [recentReqs, setRecentReqs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [taskFilter, setTaskFilter] = useState<string | undefined>();
  const [dateRange, setDateRange] = useState<[string | null, string | null]>([null, null]);

  const load = () => {
    setLoading(true);
    Promise.all([
      getRoutingDecisions({ limit: 100, date_from: dateRange[0] || undefined, date_to: dateRange[1] || undefined }),
      getRoutingPerformance(taskFilter),
      getModelLeaderboard().catch(() => ({ data: [] })),
      getRecentRequests(30).catch(() => ({ data: [] })),
    ])
      .then(([d, p, lb, rr]) => {
        setDecisions(d.data || []);
        setPerformance(p.data || []);
        setLeaderboard(lb.data || []);
        setRecentReqs(rr.data || []);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(load, [taskFilter, dateRange]);

  if (loading) return <PageSkeleton type="table" />;

  // Compute KPIs from recent requests
  const totalReqs = recentReqs.length;
  const localReqs = recentReqs.filter((r: any) => r.is_local).length;
  const localPct = totalReqs > 0 ? Math.round((localReqs / totalReqs) * 100) : 0;
  const avgLatency = totalReqs > 0 ? Math.round(recentReqs.reduce((s: number, r: any) => s + r.latency_ms, 0) / totalReqs) : 0;
  const taskTypes = [...new Set(recentReqs.map((r: any) => r.task_type).filter(Boolean))];
  const models = [...new Set(recentReqs.map((r: any) => r.model).filter(Boolean))];

  const decisionColumns: ColumnsType<any> = [
    {
      title: 'Time', dataIndex: 'created_at', width: 130,
      render: (d: string) => d ? (
        <Space direction="vertical" size={0}>
          <span style={{ fontSize: 11 }}>{dayjs(d).format('HH:mm:ss')}</span>
          <span style={{ fontSize: 9, color: '#6b7280' }}>{dayjs(d).fromNow()}</span>
        </Space>
      ) : '—',
    },
    {
      title: 'Provider', dataIndex: 'provider', width: 100,
      render: (p: string) => <Tag color={p === 'ollama' ? 'green' : p === 'claude-cli' ? 'blue' : 'purple'} style={{ fontSize: 10 }}>{p}</Tag>,
      filters: [...new Set(decisions.map((d) => d.provider))].map((p) => ({ text: p, value: p })),
      onFilter: (v, r) => r.provider === v,
    },
    {
      title: 'Model', dataIndex: 'model', width: 180, ellipsis: true,
      render: (m: string) => <span style={{ fontFamily: 'monospace', fontSize: 11 }}>{m}</span>,
    },
    {
      title: 'Task', dataIndex: 'task_type', width: 100,
      render: (t: string) => <Tag color="gold" style={{ fontSize: 10 }}>{t || 'general'}</Tag>,
      filters: taskTypes.map((t) => ({ text: t, value: t })),
      onFilter: (v, r) => r.task_type === v,
    },
    {
      title: 'Strategy', dataIndex: 'strategy', width: 100,
      render: (s: string) => (
        <Tag color={s === 'distillation' ? 'magenta' : s === 'best_quality' ? 'blue' : 'green'} style={{ fontSize: 10 }}>
          {s || '—'}
        </Tag>
      ),
    },
    {
      title: 'Latency', dataIndex: 'latency_ms', width: 90,
      sorter: (a: any, b: any) => a.latency_ms - b.latency_ms,
      render: (v: number) => (
        <span style={{ color: v > 10000 ? '#ef4444' : v > 3000 ? '#f59e0b' : '#10b981', fontSize: 11, fontWeight: 600 }}>
          {v > 1000 ? `${(v / 1000).toFixed(1)}s` : `${v}ms`}
        </span>
      ),
    },
    {
      title: 'Cost', dataIndex: 'cost_usd', width: 80,
      sorter: (a: any, b: any) => a.cost_usd - b.cost_usd,
      render: (v: number) => (
        <span style={{ color: v > 0 ? '#f59e0b' : '#10b981', fontSize: 11 }}>
          {v > 0 ? `$${v?.toFixed(4)}` : 'FREE'}
        </span>
      ),
    },
    {
      title: 'Tokens', key: 'tokens', width: 110,
      render: (_: any, r: any) => (
        <span style={{ fontSize: 10 }}>
          <Tag color="blue" style={{ fontSize: 9, margin: 0 }}>{r.prompt_tokens} in</Tag>
          {' '}
          <Tag color="purple" style={{ fontSize: 9, margin: 0 }}>{r.completion_tokens} out</Tag>
        </span>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div>
          <Typography.Title level={4} style={{ margin: 0 }}>Routing</Typography.Title>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Smart routing decisions, model performance, and task classification
          </Typography.Text>
        </div>
        <Button icon={<ReloadOutlined />} onClick={load} size="small">Refresh</Button>
      </div>

      {/* KPI Cards */}
      <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={6} md={4}>
          <Card size="small">
            <Statistic title="Decisions" value={decisions.length || totalReqs} prefix={<BranchesOutlined />} valueStyle={{ color: '#3b82f6' }} />
          </Card>
        </Col>
        <Col xs={12} sm={6} md={4}>
          <Card size="small">
            <Statistic title="Local %" value={localPct} suffix="%" prefix={<CheckCircleOutlined />} valueStyle={{ color: '#10b981' }} />
          </Card>
        </Col>
        <Col xs={12} sm={6} md={4}>
          <Card size="small">
            <Statistic title="Avg Latency" value={avgLatency > 1000 ? `${(avgLatency / 1000).toFixed(1)}s` : `${avgLatency}ms`}
              prefix={<ClockCircleOutlined />}
              valueStyle={{ color: avgLatency > 10000 ? '#ef4444' : avgLatency > 3000 ? '#f59e0b' : '#10b981' }} />
          </Card>
        </Col>
        <Col xs={12} sm={6} md={4}>
          <Card size="small">
            <Statistic title="Task Types" value={taskTypes.length} prefix={<ThunderboltOutlined />} valueStyle={{ color: '#8b5cf6' }} />
          </Card>
        </Col>
        <Col xs={12} sm={6} md={4}>
          <Card size="small">
            <Statistic title="Models Used" value={models.length} prefix={<RocketOutlined />} valueStyle={{ color: '#f59e0b' }} />
          </Card>
        </Col>
        <Col xs={12} sm={6} md={4}>
          <Card size="small">
            <Statistic title="Errors" value={recentReqs.filter((r: any) => r.error).length}
              valueStyle={{ color: recentReqs.some((r: any) => r.error) ? '#ef4444' : '#10b981' }} />
          </Card>
        </Col>
      </Row>

      {/* Model Leaderboard */}
      <Card title="Model Leaderboard" size="small" style={{ marginBottom: 12 }}
        extra={<Select placeholder="Filter task type" allowClear onChange={setTaskFilter} style={{ width: 160 }}
          options={taskTypes.map((t) => ({ value: t, label: t }))} />}
      >
        {leaderboard.length > 0 ? (
          <Table columns={[
            { title: 'Model', dataIndex: 'model', render: (m: string) => <span style={{ fontFamily: 'monospace', fontSize: 11 }}>{m}</span> },
            { title: 'Requests', dataIndex: 'requests', width: 80, sorter: (a: any, b: any) => a.requests - b.requests },
            { title: 'Tokens In', dataIndex: 'prompt_tokens', width: 90, render: (v: number) => v?.toLocaleString(), sorter: (a: any, b: any) => a.prompt_tokens - b.prompt_tokens },
            { title: 'Tokens Out', dataIndex: 'completion_tokens', width: 90, render: (v: number) => v?.toLocaleString(), sorter: (a: any, b: any) => a.completion_tokens - b.completion_tokens },
            { title: 'Avg Latency', dataIndex: 'avg_latency_ms', width: 100, sorter: (a: any, b: any) => a.avg_latency_ms - b.avg_latency_ms,
              render: (v: number) => <span style={{ color: v > 10000 ? '#ef4444' : v > 3000 ? '#f59e0b' : '#10b981' }}>{v > 1000 ? `${(v / 1000).toFixed(1)}s` : `${v}ms`}</span> },
            { title: 'P95', dataIndex: 'p95_latency', width: 80, render: (v: number) => v > 1000 ? `${(v / 1000).toFixed(1)}s` : `${v}ms` },
            { title: 'Cost', dataIndex: 'cost_usd', width: 80, render: (v: number) => v > 0 ? `$${v.toFixed(4)}` : 'FREE' },
            { title: 'Err %', dataIndex: 'error_rate', width: 60, render: (v: number) => <Tag color={v > 0 ? 'red' : 'green'} style={{ fontSize: 10 }}>{v}%</Tag> },
          ]} dataSource={leaderboard} rowKey="model" size="small" pagination={false} />
        ) : (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <BranchesOutlined style={{ fontSize: 36, color: '#4b5563', marginBottom: 8 }} />
            <div><Typography.Text type="secondary">Send requests to see model performance data</Typography.Text></div>
          </div>
        )}
      </Card>

      {/* Recent Decisions */}
      <Card title="Recent Routing Decisions" size="small"
        extra={<Space><DateRangeFilter value={dateRange} onChange={setDateRange} /><ExportDropdown data={decisions} filename="routing-decisions" /></Space>}
      >
        {decisions.length > 0 ? (
          <Table columns={decisionColumns} dataSource={decisions} rowKey="id" size="small"
            pagination={{ pageSize: 25, showSizeChanger: true, showTotal: (t) => `${t} decisions` }}
            scroll={{ x: 900 }} />
        ) : (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <BranchesOutlined style={{ fontSize: 36, color: '#4b5563', marginBottom: 8 }} />
            <div><Typography.Text type="secondary">Routing decisions will appear here as requests are processed</Typography.Text></div>
            <Typography.Text type="secondary" style={{ fontSize: 11 }}>
              The leaderboard above uses in-memory metrics. This table requires DB persistence.
            </Typography.Text>
          </div>
        )}
      </Card>
    </div>
  );
}
