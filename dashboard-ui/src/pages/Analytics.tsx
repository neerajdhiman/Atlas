import { useEffect, useState } from 'react';
import { Typography, Card, Statistic, Row, Col, Table, Tag, Space, Progress } from 'antd';
import {
  ThunderboltOutlined, DollarOutlined, FieldNumberOutlined, ClockCircleOutlined,
  ArrowUpOutlined, ArrowDownOutlined, CheckCircleOutlined, ApiOutlined,
  BarChartOutlined, PieChartOutlined,
} from '@ant-design/icons';
import {
  BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, AreaChart, Area, LineChart, Line,
} from 'recharts';
import {
  getMetrics, getRoutingDecisions, getModelLeaderboard, getTokenTimeseries,
  getCostTimeseries, getLocalVsExternal,
} from '../lib/api';
import DateRangeFilter from '../components/shared/DateRangeFilter';
import PageSkeleton from '../components/shared/PageSkeleton';

const COLORS = ['#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#06b6d4', '#84cc16'];

export default function Analytics() {
  const [metrics, setMetrics] = useState<any>(null);
  const [decisions, setDecisions] = useState<any[]>([]);
  const [leaderboard, setLeaderboard] = useState<any[]>([]);
  const [tokenSeries, setTokenSeries] = useState<any[]>([]);
  const [costSeries, setCostSeries] = useState<any[]>([]);
  const [localExt, setLocalExt] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [dateRange, setDateRange] = useState<[string | null, string | null]>([null, null]);

  useEffect(() => {
    Promise.all([
      getMetrics(),
      getRoutingDecisions({ limit: 200 }),
      getModelLeaderboard().catch(() => ({ data: [] })),
      getTokenTimeseries().catch(() => ({ data: [] })),
      getCostTimeseries().catch(() => ({ data: [] })),
      getLocalVsExternal().catch(() => ({})),
    ]).then(([m, d, lb, ts, cs, le]) => {
      setMetrics(m);
      setDecisions(d.data || []);
      setLeaderboard(lb.data || []);
      setTokenSeries(ts.data || []);
      setCostSeries(cs.data || []);
      setLocalExt(le);
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) return <PageSkeleton />;

  const totalTokens = (metrics?.total_prompt_tokens ?? 0) + (metrics?.total_completion_tokens ?? 0);
  const localPct = metrics?.request_count
    ? Math.round(((metrics?.local?.request_count ?? 0) / metrics.request_count) * 100)
    : 0;

  // Process decision data for charts
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
  const latencyData = Object.entries(latencyByModel).map(([name, { total, count }]) => ({
    name: name.length > 18 ? name.slice(0, 18) + '...' : name, avg_latency: Math.round(total / count),
  }));
  const tokenData = Object.entries(tokensByModel).map(([name, tokens]) => ({
    name: name.length > 18 ? name.slice(0, 18) + '...' : name, tokens,
  }));
  const taskData = metrics?.task_type_counts
    ? Object.entries(metrics.task_type_counts).map(([name, count]) => ({ name, count }))
    : [];

  const EmptyChart = ({ height = 220, text = 'No data yet — send requests to see analytics' }: { height?: number; text?: string }) => (
    <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column' }}>
      <BarChartOutlined style={{ fontSize: 32, color: '#4b5563', marginBottom: 8 }} />
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>{text}</Typography.Text>
    </div>
  );

  const formatUptime = (s: number) => {
    if (s < 60) return `${Math.round(s)}s`;
    if (s < 3600) return `${Math.round(s / 60)}m`;
    return `${Math.round(s / 3600)}h ${Math.round((s % 3600) / 60)}m`;
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>Analytics</Typography.Title>
        <DateRangeFilter value={dateRange} onChange={setDateRange} />
      </div>

      {/* KPI Cards */}
      <Row gutter={[12, 12]}>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="Total Requests" value={metrics?.request_count ?? 0} prefix={<ThunderboltOutlined />} valueStyle={{ color: '#3b82f6' }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="Total Cost" value={metrics?.total_cost_usd ?? 0} prefix="$" precision={4} valueStyle={{ color: (metrics?.total_cost_usd ?? 0) > 0 ? '#f59e0b' : '#10b981' }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="Total Tokens" value={totalTokens} prefix={<FieldNumberOutlined />} valueStyle={{ color: '#8b5cf6' }} />
            <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>
              {metrics?.total_prompt_tokens ?? 0} in / {metrics?.total_completion_tokens ?? 0} out
            </div>
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="Uptime" value={formatUptime(metrics?.uptime_seconds ?? 0)} prefix={<ClockCircleOutlined />} valueStyle={{ color: '#10b981' }} />
          </Card>
        </Col>
      </Row>

      {/* Local vs External + Savings */}
      <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
        <Col xs={24} md={8}>
          <Card size="small" title="Local vs External">
            <div style={{ textAlign: 'center' }}>
              <Progress type="dashboard" percent={localPct} strokeColor="#10b981" format={(pct) => `${pct}%`} size={120} />
              <div style={{ marginTop: 8 }}>
                <Tag color="green" icon={<CheckCircleOutlined />}>{metrics?.local?.request_count ?? 0} Local</Tag>
                <Tag color="blue">{metrics?.external?.request_count ?? 0} External</Tag>
              </div>
            </div>
          </Card>
        </Col>
        <Col xs={24} md={16}>
          <Card size="small" title="Token Usage Trend">
            {tokenSeries.length > 0 ? (
              <ResponsiveContainer width="100%" height={180}>
                <AreaChart data={tokenSeries}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="time" tick={{ fontSize: 9 }} tickFormatter={(v) => v.split('T')[1] || v} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip />
                  <Area type="monotone" dataKey="local" stackId="1" stroke="#10b981" fill="#10b981" fillOpacity={0.3} name="Local Tokens" />
                  <Area type="monotone" dataKey="external" stackId="1" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.3} name="External Tokens" />
                </AreaChart>
              </ResponsiveContainer>
            ) : <EmptyChart height={180} />}
          </Card>
        </Col>
      </Row>

      {/* Model Leaderboard */}
      <Card size="small" title="Model Performance Leaderboard" style={{ marginTop: 12 }}>
        {leaderboard.length > 0 ? (
          <Table
            dataSource={leaderboard}
            rowKey="model"
            size="small"
            pagination={false}
            columns={[
              {
                title: 'Model', dataIndex: 'model', width: 200,
                render: (m: string) => <span style={{ fontFamily: 'monospace', fontSize: 11 }}>{m}</span>,
              },
              { title: 'Requests', dataIndex: 'requests', width: 80, sorter: (a: any, b: any) => a.requests - b.requests },
              {
                title: 'Tokens (In/Out)', width: 140,
                render: (_: any, r: any) => (
                  <span style={{ fontSize: 11 }}>
                    <Tag color="blue" style={{ fontSize: 10 }}>{r.prompt_tokens.toLocaleString()} in</Tag>
                    <Tag color="purple" style={{ fontSize: 10 }}>{r.completion_tokens.toLocaleString()} out</Tag>
                  </span>
                ),
              },
              {
                title: 'Avg Latency', dataIndex: 'avg_latency_ms', width: 100,
                render: (v: number) => <span style={{ color: v > 5000 ? '#ef4444' : v > 2000 ? '#f59e0b' : '#10b981' }}>{Math.round(v)}ms</span>,
                sorter: (a: any, b: any) => a.avg_latency_ms - b.avg_latency_ms,
              },
              {
                title: 'P95 Latency', dataIndex: 'p95_latency', width: 100,
                render: (v: number) => <span style={{ fontSize: 11 }}>{v}ms</span>,
              },
              {
                title: 'Cost', dataIndex: 'cost_usd', width: 80,
                render: (v: number) => <span style={{ color: v > 0 ? '#f59e0b' : '#10b981' }}>${v.toFixed(4)}</span>,
              },
              {
                title: 'Err Rate', dataIndex: 'error_rate', width: 80,
                render: (v: number) => <Tag color={v > 0 ? 'red' : 'green'}>{v}%</Tag>,
              },
              {
                title: 'Avg Tokens/Req', dataIndex: 'avg_tokens_per_request', width: 100,
                render: (v: number) => <span style={{ fontSize: 11 }}>{Math.round(v)}</span>,
              },
            ]}
          />
        ) : <EmptyChart text="Model performance data will appear after requests are processed" />}
      </Card>

      {/* Charts Grid */}
      <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
        <Col xs={24} lg={12}>
          <Card title="Cost by Provider" size="small">
            {costData.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={costData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Bar dataKey="cost" fill="#10b981" name="Cost ($)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : <EmptyChart />}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="Avg Latency by Model" size="small">
            {latencyData.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={latencyData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis type="number" tick={{ fontSize: 11 }} />
                  <YAxis type="category" dataKey="name" tick={{ fontSize: 10 }} width={130} />
                  <Tooltip />
                  <Bar dataKey="avg_latency" fill="#f59e0b" name="Latency (ms)" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : <EmptyChart />}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="Token Usage by Model" size="small">
            {tokenData.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie data={tokenData} dataKey="tokens" nameKey="name" cx="50%" cy="50%" outerRadius={80} innerRadius={40}>
                    {tokenData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            ) : <EmptyChart />}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="Task Type Distribution" size="small">
            {taskData.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={taskData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#8b5cf6" name="Requests" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : <EmptyChart />}
          </Card>
        </Col>
      </Row>
    </div>
  );
}
