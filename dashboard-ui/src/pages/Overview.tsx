import { useEffect, useState } from 'react';
import { Row, Col, Card, Statistic, Tag, List, Typography, Badge, Table, Space, Button, Progress } from 'antd';
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
  ReloadOutlined,
  ApiOutlined,
} from '@ant-design/icons';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, AreaChart, Area, XAxis, YAxis, CartesianGrid } from 'recharts';
import { getOverview, getModelLeaderboard, getRecentRequests, getTokenTimeseries } from '../lib/api';
import { useWebSocketStore } from '../stores/websocketStore';
import PageSkeleton from '../components/shared/PageSkeleton';
import type { OverviewData } from '../types';

const { Text } = Typography;
const COLORS = ['#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#06b6d4', '#84cc16'];

export default function Overview() {
  const [data, setData] = useState<OverviewData | null>(null);
  const [leaderboard, setLeaderboard] = useState<any[]>([]);
  const [recentReqs, setRecentReqs] = useState<any[]>([]);
  const [tokenSeries, setTokenSeries] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const wsSubscribe = useWebSocketStore((s) => s.subscribe);
  const wsConnect = useWebSocketStore((s) => s.connect);

  const loadAll = () => {
    Promise.all([
      getOverview(),
      getModelLeaderboard().catch(() => ({ data: [] })),
      getRecentRequests(20).catch(() => ({ data: [] })),
      getTokenTimeseries().catch(() => ({ data: [] })),
    ]).then(([overview, lb, rr, ts]) => {
      setData(overview);
      setLeaderboard(lb.data || []);
      setRecentReqs(rr.data || []);
      setTokenSeries(ts.data || []);
    }).catch(() => {}).finally(() => setLoading(false));
  };

  useEffect(() => {
    loadAll();
    const interval = setInterval(loadAll, 5000);
    wsConnect();
    const unsub = wsSubscribe('*', () => {});
    return () => { clearInterval(interval); unsub(); };
  }, []);

  if (loading) return <PageSkeleton type="cards" />;

  const m = data?.metrics;
  const localPct = m?.request_count ? Math.round(((m?.local?.request_count ?? 0) / m.request_count) * 100) : 0;
  const providerData = m?.provider_counts
    ? Object.entries(m.provider_counts).map(([name, count]) => ({ name, value: count as number }))
    : [];
  const taskData = m?.task_type_counts
    ? Object.entries(m.task_type_counts).map(([name, count]) => ({ name, value: count as number }))
    : [];

  const formatUptime = (s: number) => {
    if (s < 60) return `${Math.round(s)}s`;
    if (s < 3600) return `${Math.round(s / 60)}m`;
    return `${Math.round(s / 3600)}h ${Math.round((s % 3600) / 60)}m`;
  };

  return (
    <div>
      {/* Hero: Alpheric-1 */}
      <Card size="small" style={{ marginBottom: 16, background: 'linear-gradient(135deg, rgba(59,130,246,0.12) 0%, rgba(139,92,246,0.08) 100%)', border: '1px solid rgba(59,130,246,0.2)' }}>
        <Row align="middle" gutter={24}>
          <Col flex="auto">
            <Space align="center" size={12}>
              <RocketOutlined style={{ fontSize: 28, color: '#3b82f6' }} />
              <div>
                <Typography.Title level={4} style={{ margin: 0 }}>
                  Alpheric-1 <Tag color="blue">Live</Tag>
                </Typography.Title>
                <Text type="secondary">
                  Smart-routing to {data?.providers?.filter(p => p.healthy).length ?? 0} providers, {
                    data?.providers?.reduce((sum, p) => sum + (p.models?.length ?? 0), 0) ?? 0
                  } models • Uptime: {formatUptime(m?.uptime_seconds ?? 0)}
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

      {/* KPI Cards Row 1 */}
      <Row gutter={[12, 12]}>
        {[
          { title: 'Requests', value: m?.request_count ?? 0, icon: <ThunderboltOutlined />, color: '#3b82f6' },
          { title: 'Req/min', value: m?.requests_per_minute ?? 0, icon: <DashboardOutlined />, precision: 1 },
          { title: 'Avg Latency', value: m?.avg_latency_ms ?? 0, icon: <ClockCircleOutlined />, suffix: 'ms', color: (m?.avg_latency_ms ?? 0) > 5000 ? '#ef4444' : '#10b981' },
          { title: 'Total Cost', value: m?.total_cost_usd ?? 0, icon: <DollarOutlined />, precision: 4, prefix: '$', color: (m?.total_cost_usd ?? 0) > 0 ? '#f59e0b' : '#10b981' },
          { title: 'Errors', value: m?.error_count ?? 0, icon: <WarningOutlined />, color: (m?.error_count ?? 0) > 0 ? '#ef4444' : undefined },
          { title: 'Conversations', value: data?.conversations_count ?? 0, icon: <MessageOutlined /> },
          { title: 'Providers', value: `${data?.providers?.filter(p => p.healthy).length ?? 0}/${data?.providers?.length ?? 0}`, icon: <CloudServerOutlined /> },
        ].map((stat) => (
          <Col key={stat.title} xs={12} sm={8} md={6} lg={3}>
            <Card size="small" hoverable>
              <Statistic
                title={stat.title} value={stat.value}
                prefix={stat.icon} suffix={stat.suffix}
                precision={stat.precision}
                valueStyle={stat.color ? { color: stat.color } : undefined}
              />
            </Card>
          </Col>
        ))}
      </Row>

      {/* Token Usage + Local vs External */}
      <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
        <Col xs={24} sm={8}>
          <Card size="small" style={{ borderLeft: '3px solid #10b981' }}>
            <Statistic
              title="Local Tokens (Free)"
              value={m?.local?.total_tokens ?? 0}
              valueStyle={{ color: '#10b981', fontSize: 24 }}
            />
            <Progress percent={localPct} strokeColor="#10b981" size="small" format={() => `${m?.local?.request_count ?? 0} requests`} />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card size="small" style={{ borderLeft: '3px solid #3b82f6' }}>
            <Statistic
              title="External Tokens (Paid)"
              value={m?.external?.total_tokens ?? 0}
              valueStyle={{ color: '#3b82f6', fontSize: 24 }}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>Cost: ${m?.external?.cost_usd ?? 0}</Text>
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card size="small" style={{ borderLeft: '3px solid #f59e0b' }}>
            <Statistic
              title="Savings vs External"
              value={m?.savings_usd ?? 0}
              prefix="$" precision={4}
              valueStyle={{ color: '#f59e0b', fontSize: 24 }}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>Compared to gpt-4o-mini pricing</Text>
          </Card>
        </Col>
      </Row>

      {/* Token Timeseries + Charts + Live Feed */}
      <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
        {/* Token time-series chart */}
        <Col xs={24} lg={16}>
          <Card title="Token Usage Over Time" size="small">
            {tokenSeries.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={tokenSeries}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="time" tick={{ fontSize: 10 }} tickFormatter={(v) => v.split('T')[1] || v} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip />
                  <Area type="monotone" dataKey="prompt" stackId="1" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.3} name="Input Tokens" />
                  <Area type="monotone" dataKey="completion" stackId="1" stroke="#8b5cf6" fill="#8b5cf6" fillOpacity={0.3} name="Output Tokens" />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column' }}>
                <ApiOutlined style={{ fontSize: 32, color: '#4b5563', marginBottom: 8 }} />
                <Text type="secondary">Send requests to see token usage trends</Text>
              </div>
            )}
          </Card>
        </Col>

        {/* Live Feed */}
        <Col xs={24} lg={8}>
          <Card title={<span>Recent Requests <Badge dot status="success" style={{ marginLeft: 8 }} /></span>} size="small">
            <List
              dataSource={recentReqs}
              locale={{ emptyText: 'No requests yet — try the Playground!' }}
              style={{ height: 200, overflowY: 'auto' }}
              renderItem={(e: any) => (
                <List.Item style={{ padding: '3px 0', borderBottom: 'none' }}>
                  <div style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 6, fontSize: 11 }}>
                    <Tag color={e.is_local ? 'green' : 'blue'} style={{ fontSize: 10, margin: 0 }}>
                      {e.is_local ? 'LOCAL' : 'EXT'}
                    </Tag>
                    <Text style={{ fontSize: 11, flex: 1 }} ellipsis>{e.model}</Text>
                    <Text type="secondary" style={{ fontSize: 10 }}>{e.prompt_tokens}→{e.completion_tokens}t</Text>
                    <Text style={{ fontSize: 10, color: e.latency_ms > 5000 ? '#ef4444' : '#10b981' }}>
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
                    <Pie data={providerData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={60} innerRadius={30}>
                      {providerData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                  {providerData.map((d, i) => (
                    <Tag key={d.name} color={COLORS[i % COLORS.length]}>{d.name}: {d.value}</Tag>
                  ))}
                </div>
              </>
            ) : (
              <div style={{ height: 180, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column' }}>
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
                  <Pie data={taskData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={60} innerRadius={30}>
                    {taskData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column' }}>
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
                  { title: 'Model', dataIndex: 'model', render: (m: string) => <Text style={{ fontSize: 11, fontFamily: 'monospace' }}>{m}</Text> },
                  { title: 'Reqs', dataIndex: 'requests', width: 50 },
                  { title: 'Avg ms', dataIndex: 'avg_latency_ms', width: 65, render: (v: number) => <span style={{ color: v > 5000 ? '#ef4444' : '#10b981' }}>{Math.round(v)}</span> },
                  { title: 'Tokens', dataIndex: 'total_tokens', width: 65, render: (v: number) => v.toLocaleString() },
                ]}
              />
            ) : (
              <div style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column' }}>
                <DashboardOutlined style={{ fontSize: 32, color: '#4b5563', marginBottom: 8 }} />
                <Text type="secondary">Model performance data will appear here</Text>
              </div>
            )}
          </Card>
        </Col>
      </Row>

      {/* Server Health */}
      <Card title="Infrastructure Health" size="small" style={{ marginTop: 12 }}>
        <Row gutter={[12, 12]}>
          {(data?.providers ?? []).map((p) => (
            <Col key={p.name} xs={12} sm={8} md={6}>
              <Card size="small" style={{ borderLeft: `3px solid ${p.healthy ? '#10b981' : '#ef4444'}` }} hoverable>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Text strong style={{ textTransform: 'capitalize' }}>{p.name}</Text>
                  <Tag color={p.healthy ? 'success' : 'error'} icon={p.healthy ? <CheckCircleOutlined /> : <CloseCircleOutlined />}>
                    {p.healthy ? 'Healthy' : 'Down'}
                  </Tag>
                </div>
                <Text type="secondary" style={{ fontSize: 12 }}>{p.models?.length ?? 0} models</Text>
                <div style={{ marginTop: 4, display: 'flex', flexWrap: 'wrap', gap: 2 }}>
                  {(p.models || []).slice(0, 4).map((m: string) => (
                    <Tag key={m} style={{ fontSize: 9, margin: 0 }}>{m}</Tag>
                  ))}
                  {(p.models?.length ?? 0) > 4 && <Tag style={{ fontSize: 9 }}>+{(p.models?.length ?? 0) - 4}</Tag>}
                </div>
              </Card>
            </Col>
          ))}
        </Row>
      </Card>
    </div>
  );
}
