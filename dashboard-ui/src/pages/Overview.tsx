import { useEffect, useState } from 'react';
import { Row, Col, Card, Statistic, Tag, List, Typography, Badge } from 'antd';
import {
  ThunderboltOutlined,
  DashboardOutlined,
  ClockCircleOutlined,
  DollarOutlined,
  WarningOutlined,
  MessageOutlined,
  CloudServerOutlined,
} from '@ant-design/icons';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import { getOverview } from '../lib/api';
import { useWebSocketStore } from '../stores/websocketStore';
import PageSkeleton from '../components/shared/PageSkeleton';
import type { OverviewData } from '../types';

const { Text } = Typography;
const COLORS = ['#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#ec4899'];

export default function Overview() {
  const [data, setData] = useState<OverviewData | null>(null);
  const [liveEvents, setLiveEvents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const wsSubscribe = useWebSocketStore((s) => s.subscribe);
  const wsConnect = useWebSocketStore((s) => s.connect);

  useEffect(() => {
    getOverview().then(setData).catch(() => {}).finally(() => setLoading(false));
    const interval = setInterval(() => {
      getOverview().then(setData).catch(() => {});
    }, 5000);

    wsConnect();
    const unsub = wsSubscribe('*', (event) => {
      setLiveEvents((prev) => [event, ...prev].slice(0, 50));
    });

    return () => {
      clearInterval(interval);
      unsub();
    };
  }, []);

  if (loading) return <PageSkeleton type="cards" />;

  const m = data?.metrics;
  const providerData = m?.provider_counts
    ? Object.entries(m.provider_counts).map(([name, count]) => ({ name, value: count as number }))
    : [];
  const taskData = m?.task_type_counts
    ? Object.entries(m.task_type_counts).map(([name, count]) => ({ name, value: count as number }))
    : [];

  return (
    <div>
      <Typography.Title level={4} style={{ marginBottom: 20 }}>Overview</Typography.Title>

      {/* Stat cards */}
      <Row gutter={[16, 16]}>
        <Col xs={12} sm={8} md={6} lg={3}>
          <Card size="small"><Statistic title="Requests" value={m?.request_count ?? 0} prefix={<ThunderboltOutlined />} /></Card>
        </Col>
        <Col xs={12} sm={8} md={6} lg={3}>
          <Card size="small"><Statistic title="Req/min" value={m?.requests_per_minute ?? 0} prefix={<DashboardOutlined />} precision={1} /></Card>
        </Col>
        <Col xs={12} sm={8} md={6} lg={3}>
          <Card size="small"><Statistic title="Avg Latency" value={m?.avg_latency_ms ?? 0} suffix="ms" prefix={<ClockCircleOutlined />} /></Card>
        </Col>
        <Col xs={12} sm={8} md={6} lg={3}>
          <Card size="small"><Statistic title="Total Cost" value={m?.total_cost_usd ?? 0} prefix={<DollarOutlined />} precision={4} /></Card>
        </Col>
        <Col xs={12} sm={8} md={6} lg={3}>
          <Card size="small"><Statistic title="Errors" value={m?.error_count ?? 0} prefix={<WarningOutlined />} valueStyle={{ color: (m?.error_count ?? 0) > 0 ? '#ef4444' : undefined }} /></Card>
        </Col>
        <Col xs={12} sm={8} md={6} lg={3}>
          <Card size="small"><Statistic title="Conversations" value={data?.conversations_count ?? 0} prefix={<MessageOutlined />} /></Card>
        </Col>
        <Col xs={12} sm={8} md={6} lg={3}>
          <Card size="small">
            <Statistic
              title="Providers"
              value={`${data?.providers?.filter((p) => p.healthy).length ?? 0}/${data?.providers?.length ?? 0}`}
              prefix={<CloudServerOutlined />}
            />
          </Card>
        </Col>
      </Row>

      {/* Charts + Live Feed */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={8}>
          <Card title="Provider Distribution" size="small">
            {providerData.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie data={providerData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={70}>
                    {providerData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Text type="secondary">No data yet</Text>
              </div>
            )}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 8 }}>
              {providerData.map((d, i) => (
                <Tag key={d.name} color={COLORS[i % COLORS.length]}>{d.name}: {d.value}</Tag>
              ))}
            </div>
          </Card>
        </Col>

        <Col xs={24} lg={8}>
          <Card title="Task Types" size="small">
            {taskData.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie data={taskData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={70}>
                    {taskData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Text type="secondary">No data yet</Text>
              </div>
            )}
          </Card>
        </Col>

        <Col xs={24} lg={8}>
          <Card title={<span>Live Feed <Badge dot status="success" style={{ marginLeft: 8 }} /></span>} size="small">
            <List
              dataSource={liveEvents}
              locale={{ emptyText: 'Waiting for requests...' }}
              style={{ height: 220, overflowY: 'auto' }}
              renderItem={(e: any) => (
                <List.Item style={{ padding: '4px 0', borderBottom: 'none' }}>
                  <Text type="secondary" style={{ fontSize: 11, marginRight: 8 }}>
                    {new Date(e.timestamp || Date.now()).toLocaleTimeString()}
                  </Text>
                  <Tag color={e.error ? 'red' : 'blue'}>{e.provider || '?'}</Tag>
                  <Text style={{ fontSize: 12 }}>{e.model || '—'}</Text>
                  <Text type="secondary" style={{ fontSize: 11, marginLeft: 'auto' }}>{e.latency_ms}ms</Text>
                </List.Item>
              )}
            />
          </Card>
        </Col>
      </Row>

      {/* Provider Health */}
      <Card title="Provider Health" size="small" style={{ marginTop: 16 }}>
        <Row gutter={[12, 12]}>
          {(data?.providers ?? []).map((p) => (
            <Col key={p.name} xs={12} sm={8} md={6}>
              <Card size="small" style={{ borderLeft: `3px solid ${p.healthy ? '#10b981' : '#ef4444'}` }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Text strong style={{ textTransform: 'capitalize' }}>{p.name}</Text>
                  <Tag color={p.healthy ? 'success' : 'error'}>{p.healthy ? 'Healthy' : 'Down'}</Tag>
                </div>
                <Text type="secondary" style={{ fontSize: 12 }}>{p.models?.length ?? 0} models</Text>
              </Card>
            </Col>
          ))}
        </Row>
      </Card>
    </div>
  );
}
