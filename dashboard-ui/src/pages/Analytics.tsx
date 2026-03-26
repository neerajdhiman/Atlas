import { useEffect, useState } from 'react';
import { Typography, Card, Statistic, Row, Col } from 'antd';
import { ThunderboltOutlined, DollarOutlined, FieldNumberOutlined, ClockCircleOutlined } from '@ant-design/icons';
import { BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { getMetrics, getRoutingDecisions } from '../lib/api';
import DateRangeFilter from '../components/shared/DateRangeFilter';
import PageSkeleton from '../components/shared/PageSkeleton';

const COLORS = ['#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#ec4899'];

export default function Analytics() {
  const [metrics, setMetrics] = useState<any>(null);
  const [decisions, setDecisions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [dateRange, setDateRange] = useState<[string | null, string | null]>([null, null]);

  useEffect(() => {
    Promise.all([getMetrics(), getRoutingDecisions({ limit: 200 })])
      .then(([m, d]) => { setMetrics(m); setDecisions(d.data || []); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <PageSkeleton />;

  const costByProvider: Record<string, number> = {};
  const latencyByModel: Record<string, { total: number; count: number }> = {};
  const tokensByModel: Record<string, number> = {};

  for (const d of decisions) {
    costByProvider[d.provider] = (costByProvider[d.provider] || 0) + (d.cost_usd || 0);
    if (!latencyByModel[d.model]) latencyByModel[d.model] = { total: 0, count: 0 };
    latencyByModel[d.model].total += d.latency_ms || 0;
    latencyByModel[d.model].count += 1;
    tokensByModel[d.model] = (tokensByModel[d.model] || 0) + (d.prompt_tokens || 0) + (d.completion_tokens || 0);
  }

  const costData = Object.entries(costByProvider).map(([name, cost]) => ({ name, cost: +cost.toFixed(4) }));
  const latencyData = Object.entries(latencyByModel).map(([name, { total, count }]) => ({ name: name.length > 20 ? name.slice(0, 20) + '...' : name, avg_latency: Math.round(total / count) }));
  const tokenData = Object.entries(tokensByModel).map(([name, tokens]) => ({ name: name.length > 20 ? name.slice(0, 20) + '...' : name, tokens }));
  const taskData = metrics?.task_type_counts ? Object.entries(metrics.task_type_counts).map(([name, count]) => ({ name, count })) : [];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>Analytics</Typography.Title>
        <DateRangeFilter value={dateRange} onChange={setDateRange} />
      </div>

      <Row gutter={[16, 16]}>
        <Col xs={12} sm={6}><Card size="small"><Statistic title="Total Requests" value={metrics?.request_count ?? 0} prefix={<ThunderboltOutlined />} /></Card></Col>
        <Col xs={12} sm={6}><Card size="small"><Statistic title="Total Cost" value={metrics?.total_cost_usd ?? 0} prefix={<DollarOutlined />} precision={4} /></Card></Col>
        <Col xs={12} sm={6}><Card size="small"><Statistic title="Total Tokens" value={(metrics?.total_prompt_tokens ?? 0) + (metrics?.total_completion_tokens ?? 0)} prefix={<FieldNumberOutlined />} /></Card></Col>
        <Col xs={12} sm={6}><Card size="small"><Statistic title="Uptime" value={metrics?.uptime_seconds ? `${Math.round(metrics.uptime_seconds / 60)}m` : '—'} prefix={<ClockCircleOutlined />} /></Card></Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={12}>
          <Card title="Cost by Provider" size="small">
            {costData.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={costData}><CartesianGrid strokeDasharray="3 3" stroke="#374151" /><XAxis dataKey="name" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} /><Tooltip /><Bar dataKey="cost" fill="#10b981" name="Cost ($)" radius={[4, 4, 0, 0]} /></BarChart>
              </ResponsiveContainer>
            ) : <div style={{ height: 250, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#6b7280' }}>No data</div>}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="Avg Latency by Model" size="small">
            {latencyData.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={latencyData}><CartesianGrid strokeDasharray="3 3" stroke="#374151" /><XAxis dataKey="name" tick={{ fontSize: 10 }} /><YAxis tick={{ fontSize: 11 }} /><Tooltip /><Bar dataKey="avg_latency" fill="#f59e0b" name="Latency (ms)" radius={[4, 4, 0, 0]} /></BarChart>
              </ResponsiveContainer>
            ) : <div style={{ height: 250, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#6b7280' }}>No data</div>}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="Token Usage by Model" size="small">
            {tokenData.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <PieChart><Pie data={tokenData} dataKey="tokens" nameKey="name" cx="50%" cy="50%" outerRadius={90}>{tokenData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}</Pie><Tooltip /></PieChart>
              </ResponsiveContainer>
            ) : <div style={{ height: 250, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#6b7280' }}>No data</div>}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="Task Type Distribution" size="small">
            {taskData.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={taskData}><CartesianGrid strokeDasharray="3 3" stroke="#374151" /><XAxis dataKey="name" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} /><Tooltip /><Bar dataKey="count" fill="#8b5cf6" name="Requests" radius={[4, 4, 0, 0]} /></BarChart>
              </ResponsiveContainer>
            ) : <div style={{ height: 250, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#6b7280' }}>No data</div>}
          </Card>
        </Col>
      </Row>
    </div>
  );
}
