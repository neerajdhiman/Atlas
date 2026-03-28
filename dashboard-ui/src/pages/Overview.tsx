import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Row, Col, Card, Tag, List, Typography, Badge, Table, Space, Progress } from 'antd';
import {
  ThunderboltOutlined,
  DashboardOutlined,
  ClockCircleOutlined,
  DollarOutlined,
  WarningOutlined,
  MessageOutlined,
  CloudServerOutlined,
  RocketOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ApiOutlined,
} from '@ant-design/icons';
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
} from 'recharts';
import { getOverview, getModelLeaderboard, getRecentRequests, getTokenTimeseries } from '../lib/api';
import { useWebSocketStore } from '../stores/websocketStore';
import PageSkeleton from '../components/shared/PageSkeleton';
import StatsCard from '../components/shared/StatsCard';
import { COLORS, LATENCY_WARN_MS } from '../lib/tokens';
import type { OverviewData } from '../types';

const { Text } = Typography;

const formatUptime = (s: number) => {
  if (s < 60) return `${Math.round(s)}s`;
  if (s < 3600) return `${Math.round(s / 60)}m`;
  return `${Math.round(s / 3600)}h ${Math.round((s % 3600) / 60)}m`;
};

export default function Overview() {
  const wsSubscribe = useWebSocketStore((s) => s.subscribe);
  const wsConnect = useWebSocketStore((s) => s.connect);

  // React Query replaces useEffect + setInterval — no manual cleanup needed
  const { data, isLoading } = useQuery<OverviewData>({
    queryKey: ['overview'],
    queryFn: getOverview,
    refetchInterval: 5_000,
  });

  const { data: leaderboard = [] } = useQuery<any[]>({
    queryKey: ['modelLeaderboard'],
    queryFn: async () => {
      const r = await getModelLeaderboard();
      return r.data ?? [];
    },
    refetchInterval: 5_000,
  });

  const { data: recentReqs = [] } = useQuery<any[]>({
    queryKey: ['recentRequests'],
    queryFn: async () => {
      const r = await getRecentRequests(20);
      return r.data ?? [];
    },
    refetchInterval: 5_000,
  });

  const { data: tokenSeries = [] } = useQuery<any[]>({
    queryKey: ['tokenTimeseries'],
    queryFn: async () => {
      const r = await getTokenTimeseries();
      return r.data ?? [];
    },
    refetchInterval: 5_000,
  });

  // Keep WebSocket live-feed connected for real-time events
  useEffect(() => {
    wsConnect();
    const unsub = wsSubscribe('*', () => {});
    return () => unsub();
  }, []);

  if (isLoading) return <PageSkeleton type="cards" />;

  const m = data?.metrics;
  const localPct = m?.request_count
    ? Math.round(((m?.local?.request_count ?? 0) / m.request_count) * 100)
    : 0;
  const providerData = m?.provider_counts
    ? Object.entries(m.provider_counts).map(([name, count]) => ({ name, value: count as number }))
    : [];
  const taskData = m?.task_type_counts
    ? Object.entries(m.task_type_counts).map(([name, count]) => ({ name, value: count as number }))
    : [];

  const kpiStats = [
    { title: 'Requests', value: m?.request_count ?? 0, icon: <ThunderboltOutlined />, color: '#3b82f6' },
    { title: 'Req/min', value: m?.requests_per_minute ?? 0, icon: <DashboardOutlined />, precision: 1 },
    {
      title: 'Avg Latency',
      value: m?.avg_latency_ms ?? 0,
      icon: <ClockCircleOutlined />,
      suffix: 'ms',
      color: (m?.avg_latency_ms ?? 0) > LATENCY_WARN_MS ? '#ef4444' : '#10b981',
    },
    {
      title: 'Total Cost',
      value: m?.total_cost_usd ?? 0,
      icon: <DollarOutlined />,
      precision: 4,
      color: (m?.total_cost_usd ?? 0) > 0 ? '#f59e0b' : '#10b981',
    },
    {
      title: 'Errors',
      value: m?.error_count ?? 0,
      icon: <WarningOutlined />,
      color: (m?.error_count ?? 0) > 0 ? '#ef4444' : undefined,
    },
    { title: 'Conversations', value: data?.conversations_count ?? 0, icon: <MessageOutlined /> },
    {
      title: 'Providers',
      value: `${data?.providers?.filter((p) => p.healthy).length ?? 0}/${data?.providers?.length ?? 0}`,
      icon: <CloudServerOutlined />,
    },
  ];

  return (
    <div>
      {/* Hero */}
      <Card
        size="small"
        style={{
          marginBottom: 16,
          background:
            'linear-gradient(135deg, rgba(59,130,246,0.12) 0%, rgba(139,92,246,0.08) 100%)',
          border: '1px solid rgba(59,130,246,0.2)',
        }}
      >
        <Row align="middle" gutter={24}>
          <Col flex="auto">
            <Space align="center" size={12}>
              <RocketOutlined style={{ fontSize: 28, color: '#3b82f6' }} />
              <div>
                <Typography.Title level={4} style={{ margin: 0 }}>
                  Alpheric.AI — Atlas <Tag color="blue">Live</Tag>
                </Typography.Title>
                <Text type="secondary">
                  Smart-routing to {data?.providers?.filter((p) => p.healthy).length ?? 0} providers,{' '}
                  {data?.providers?.reduce((sum, p) => sum + (p.models?.length ?? 0), 0) ?? 0} models
                  • Uptime: {formatUptime(m?.uptime_seconds ?? 0)}
                </Text>
              </div>
            </Space>
          </Col>
          <Col>
            <Space>
              <Tag color="green" icon={<CheckCircleOutlined />}>
                {localPct}% Local
              </Tag>
              <Tag color="gold">
                {m?.total_prompt_tokens ?? 0} tokens in / {m?.total_completion_tokens ?? 0} out
              </Tag>
            </Space>
          </Col>
        </Row>
      </Card>

      {/* KPI Cards — StatsCard shared component */}
      <Row gutter={[12, 12]}>
        {kpiStats.map((stat) => (
          <Col key={stat.title} xs={12} sm={8} md={6} lg={3}>
            <StatsCard {...stat} />
          </Col>
        ))}
      </Row>

      {/* Token Usage + Local vs External */}
      <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
        <Col xs={24} sm={8}>
          <Card size="small" style={{ borderLeft: '3px solid #10b981' }}>
            <StatsCard
              title="Local Tokens (Free)"
              value={m?.local?.total_tokens ?? 0}
              color="#10b981"
              hoverable={false}
            />
            <Progress
              percent={localPct}
              strokeColor="#10b981"
              size="small"
              format={() => `${m?.local?.request_count ?? 0} requests`}
            />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card size="small" style={{ borderLeft: '3px solid #3b82f6' }}>
            <StatsCard
              title="External Tokens (Paid)"
              value={m?.external?.total_tokens ?? 0}
              color="#3b82f6"
              hoverable={false}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              Cost: ${m?.external?.cost_usd ?? 0}
            </Text>
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card size="small" style={{ borderLeft: '3px solid #f59e0b' }}>
            <StatsCard
              title="Savings vs External"
              value={m?.savings_usd ?? 0}
              precision={4}
              color="#f59e0b"
              hoverable={false}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              Compared to gpt-4o-mini pricing
            </Text>
          </Card>
        </Col>
      </Row>

      {/* Token Timeseries + Live Feed */}
      <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
        <Col xs={24} lg={16}>
          <Card title="Token Usage Over Time" size="small">
            {tokenSeries.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={tokenSeries}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis
                    dataKey="time"
                    tick={{ fontSize: 10 }}
                    tickFormatter={(v) => v.split('T')[1] || v}
                  />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip />
                  <Area
                    type="monotone"
                    dataKey="prompt"
                    stackId="1"
                    stroke="#3b82f6"
                    fill="#3b82f6"
                    fillOpacity={0.3}
                    name="Input Tokens"
                  />
                  <Area
                    type="monotone"
                    dataKey="completion"
                    stackId="1"
                    stroke="#8b5cf6"
                    fill="#8b5cf6"
                    fillOpacity={0.3}
                    name="Output Tokens"
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div
                style={{
                  height: 200,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexDirection: 'column',
                }}
              >
                <ApiOutlined style={{ fontSize: 32, color: '#4b5563', marginBottom: 8 }} />
                <Text type="secondary">Send requests to see token usage trends</Text>
              </div>
            )}
          </Card>
        </Col>

        <Col xs={24} lg={8}>
          <Card
            title={
              <span>
                Recent Requests <Badge dot status="success" style={{ marginLeft: 8 }} />
              </span>
            }
            size="small"
          >
            <List
              dataSource={recentReqs}
              locale={{ emptyText: 'No requests yet — try the Playground!' }}
              style={{ height: 200, overflowY: 'auto' }}
              renderItem={(e: any) => (
                <List.Item style={{ padding: '3px 0', borderBottom: 'none' }}>
                  <div
                    style={{
                      width: '100%',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      fontSize: 11,
                    }}
                  >
                    <Tag
                      color={e.is_local ? 'green' : 'blue'}
                      style={{ fontSize: 10, margin: 0 }}
                    >
                      {e.is_local ? 'LOCAL' : 'EXT'}
                    </Tag>
                    <Text style={{ fontSize: 11, flex: 1 }} ellipsis>
                      {e.model}
                    </Text>
                    <Text type="secondary" style={{ fontSize: 10 }}>
                      {e.prompt_tokens}→{e.completion_tokens}t
                    </Text>
                    <Text
                      style={{
                        fontSize: 10,
                        color: e.latency_ms > LATENCY_WARN_MS ? '#ef4444' : '#10b981',
                      }}
                    >
                      {e.latency_ms}ms
                    </Text>
                  </div>
                </List.Item>
              )}
            />
          </Card>
        </Col>
      </Row>

      {/* Charts Row */}
      <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
        <Col xs={24} lg={8}>
          <Card title="Provider Distribution" size="small">
            {providerData.length > 0 ? (
              <>
                <ResponsiveContainer width="100%" height={180}>
                  <PieChart>
                    <Pie
                      data={providerData}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      outerRadius={60}
                      innerRadius={30}
                    >
                      {providerData.map((_, i) => (
                        <Cell key={i} fill={COLORS[i % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                  {providerData.map((d, i) => (
                    <Tag key={d.name} color={COLORS[i % COLORS.length]}>
                      {d.name}: {d.value}
                    </Tag>
                  ))}
                </div>
              </>
            ) : (
              <div
                style={{
                  height: 180,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexDirection: 'column',
                }}
              >
                <CloudServerOutlined style={{ fontSize: 32, color: '#4b5563', marginBottom: 8 }} />
                <Text type="secondary">No provider data yet</Text>
              </div>
            )}
          </Card>
        </Col>

        <Col xs={24} lg={8}>
          <Card title="Task Types" size="small">
            {taskData.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie
                    data={taskData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={60}
                    innerRadius={30}
                  >
                    {taskData.map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div
                style={{
                  height: 200,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexDirection: 'column',
                }}
              >
                <ThunderboltOutlined style={{ fontSize: 32, color: '#4b5563', marginBottom: 8 }} />
                <Text type="secondary">Task classification data will appear here</Text>
              </div>
            )}
          </Card>
        </Col>

        <Col xs={24} lg={8}>
          <Card title="Model Leaderboard" size="small">
            {leaderboard.length > 0 ? (
              <Table
                dataSource={leaderboard.slice(0, 5)}
                rowKey="model"
                size="small"
                pagination={false}
                columns={[
                  {
                    title: 'Model',
                    dataIndex: 'model',
                    render: (model: string) => (
                      <Text style={{ fontSize: 11, fontFamily: 'monospace' }}>{model}</Text>
                    ),
                  },
                  { title: 'Reqs', dataIndex: 'requests', width: 50 },
                  {
                    title: 'Avg ms',
                    dataIndex: 'avg_latency_ms',
                    width: 65,
                    render: (v: number) => (
                      <span style={{ color: v > LATENCY_WARN_MS ? '#ef4444' : '#10b981' }}>
                        {Math.round(v)}
                      </span>
                    ),
                  },
                  {
                    title: 'Tokens',
                    dataIndex: 'total_tokens',
                    width: 65,
                    render: (v: number) => v.toLocaleString(),
                  },
                ]}
              />
            ) : (
              <div
                style={{
                  height: 200,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexDirection: 'column',
                }}
              >
                <DashboardOutlined style={{ fontSize: 32, color: '#4b5563', marginBottom: 8 }} />
                <Text type="secondary">Model performance data will appear here</Text>
              </div>
            )}
          </Card>
        </Col>
      </Row>

      {/* Infrastructure Health */}
      <Card title="Infrastructure Health" size="small" style={{ marginTop: 12 }}>
        <Row gutter={[12, 12]}>
          {(data?.providers ?? []).map((p) => (
            <Col key={p.name} xs={12} sm={8} md={6}>
              <Card
                size="small"
                style={{ borderLeft: `3px solid ${p.healthy ? '#10b981' : '#ef4444'}` }}
                hoverable
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}
                >
                  <Text strong style={{ textTransform: 'capitalize' }}>
                    {p.name}
                  </Text>
                  <Tag
                    color={p.healthy ? 'success' : 'error'}
                    icon={p.healthy ? <CheckCircleOutlined /> : <CloseCircleOutlined />}
                  >
                    {p.healthy ? 'Healthy' : 'Down'}
                  </Tag>
                </div>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {p.models?.length ?? 0} models
                </Text>
                <div style={{ marginTop: 4, display: 'flex', flexWrap: 'wrap', gap: 2 }}>
                  {(p.models || []).slice(0, 4).map((model: string) => (
                    <Tag key={model} style={{ fontSize: 9, margin: 0 }}>
                      {model}
                    </Tag>
                  ))}
                  {(p.models?.length ?? 0) > 4 && (
                    <Tag style={{ fontSize: 9 }}>+{(p.models?.length ?? 0) - 4}</Tag>
                  )}
                </div>
              </Card>
            </Col>
          ))}
        </Row>
      </Card>
    </div>
  );
}
