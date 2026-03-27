import { useEffect, useState } from 'react';
import {
  Typography, Table, Tag, Input, Space, Card, Row, Col, Statistic, Badge, Button,
  Tooltip, App, Progress, Segmented,
} from 'antd';
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table';
import {
  MessageOutlined, UserOutlined, ClockCircleOutlined, ThunderboltOutlined,
  CloudServerOutlined, SearchOutlined, ReloadOutlined, RocketOutlined,
  BranchesOutlined, DatabaseOutlined, ExperimentOutlined, SafetyCertificateOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip as RTooltip } from 'recharts';
import { getConversations, getConversationStats, getDistillationOverview, getSessions } from '../lib/api';
import ExportDropdown from '../components/shared/ExportDropdown';
import DateRangeFilter from '../components/shared/DateRangeFilter';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
dayjs.extend(relativeTime);

const { Search } = Input;
const COLORS = ['#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#06b6d4'];

const SOURCE_CONFIG: Record<string, { label: string; color: string; icon: any }> = {
  proxy: { label: 'Proxy', color: 'blue', icon: <ThunderboltOutlined /> },
  'import:paperclip': { label: 'Paperclip', color: 'purple', icon: <DatabaseOutlined /> },
  'import:openai_jsonl': { label: 'JSONL', color: 'orange', icon: <DatabaseOutlined /> },
  openclaw: { label: 'OpenClaw', color: 'cyan', icon: <CloudServerOutlined /> },
  distillation: { label: 'Distillation', color: 'gold', icon: <ExperimentOutlined /> },
  test: { label: 'Test', color: 'default', icon: <BranchesOutlined /> },
};

export default function Conversations() {
  const [data, setData] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<any>(null);
  const [distillation, setDistillation] = useState<any>(null);
  const [sessions, setSessions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [search, setSearch] = useState('');
  const [dateRange, setDateRange] = useState<[string | null, string | null]>([null, null]);
  const [view, setView] = useState<'conversations' | 'sessions'>('conversations');
  const navigate = useNavigate();

  const load = () => {
    setLoading(true);
    Promise.all([
      getConversations({
        limit: pageSize, offset: (page - 1) * pageSize,
        search: search || undefined,
        date_from: dateRange[0] || undefined, date_to: dateRange[1] || undefined,
      }),
      getConversationStats().catch(() => null),
      getDistillationOverview().catch(() => null),
      getSessions().catch(() => ({ data: [] })),
    ])
      .then(([res, st, dist, sess]) => {
        setData(res.data || []);
        setTotal(res.total || 0);
        setStats(st);
        setDistillation(dist);
        setSessions(sess.data || []);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(load, [page, pageSize, search, dateRange]);

  // Source pie data
  const sourcePie = stats?.sources
    ? Object.entries(stats.sources).map(([name, count]) => ({ name, value: count as number }))
    : [];

  // Distillation sample total
  const distSamples = (distillation?.task_types || []).reduce((s: number, t: any) => s + t.claude_samples, 0);

  const columns: ColumnsType<any> = [
    {
      title: 'ID', dataIndex: 'id', width: 90,
      render: (id: string) => (
        <a onClick={() => navigate(`/conversations/${id}`)} style={{ fontFamily: 'monospace', fontSize: 11 }}>
          {id.slice(0, 8)}
        </a>
      ),
    },
    {
      title: 'Source', dataIndex: 'source', width: 120,
      render: (s: string) => {
        const cfg = SOURCE_CONFIG[s] || { label: s, color: 'default', icon: <BranchesOutlined /> };
        return <Tag icon={cfg.icon} color={cfg.color} style={{ fontSize: 10 }}>{cfg.label}</Tag>;
      },
      filters: Object.entries(SOURCE_CONFIG).map(([k, v]) => ({ text: v.label, value: k })),
      onFilter: (value, record) => record.source === value,
    },
    {
      title: 'User', dataIndex: 'user_id', width: 130,
      render: (u: string | null) => u ? (
        <Space size={4}><UserOutlined style={{ fontSize: 10, color: '#6b7280' }} /><span style={{ fontSize: 11 }}>{u}</span></Space>
      ) : <span style={{ color: '#4b5563', fontSize: 11 }}>anonymous</span>,
    },
    {
      title: 'Messages', dataIndex: 'message_count', width: 85,
      sorter: (a, b) => a.message_count - b.message_count,
      render: (c: number) => (
        <Space size={4}>
          <Badge count={c} showZero color={c > 5 ? '#3b82f6' : c > 0 ? '#10b981' : '#6b7280'} style={{ fontSize: 10 }} overflowCount={999} />
          <span style={{ fontSize: 10, color: '#6b7280' }}>{c > 0 ? `${Math.ceil(c / 2)} turns` : ''}</span>
        </Space>
      ),
    },
    {
      title: 'Created', dataIndex: 'created_at', width: 150,
      sorter: (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
      defaultSortOrder: 'descend',
      render: (d: string) => d ? (
        <Space direction="vertical" size={0}>
          <span style={{ fontSize: 11 }}>{dayjs(d).format('MMM D, HH:mm')}</span>
          <span style={{ fontSize: 10, color: '#6b7280' }}>{dayjs(d).fromNow()}</span>
        </Space>
      ) : '—',
    },
  ];

  const sessionColumns: ColumnsType<any> = [
    {
      title: 'Session ID', dataIndex: 'id', width: 100,
      render: (id: string) => <span style={{ fontFamily: 'monospace', fontSize: 11 }}>{id.slice(0, 8)}...</span>,
    },
    { title: 'User', dataIndex: 'user_id', width: 120, render: (u: string | null) => u || <span style={{ color: '#4b5563' }}>—</span> },
    {
      title: 'Messages', dataIndex: 'message_count', width: 80,
      render: (c: number) => <Badge count={c} showZero color="#3b82f6" style={{ fontSize: 10 }} />,
    },
    {
      title: 'Age', dataIndex: 'age_seconds', width: 100,
      render: (s: number) => s < 60 ? `${s}s` : s < 3600 ? `${Math.round(s / 60)}m` : `${Math.round(s / 3600)}h`,
    },
    {
      title: 'Last Active', dataIndex: 'last_activity', width: 140,
      render: (t: number) => t ? dayjs.unix(t).fromNow() : '—',
    },
  ];

  const pagination: TablePaginationConfig = {
    current: page, pageSize, total,
    showSizeChanger: true, showTotal: (t) => `${t} total`,
    pageSizeOptions: [10, 25, 50, 100],
    onChange: (p, ps) => { setPage(p); setPageSize(ps); },
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div>
          <Typography.Title level={4} style={{ margin: 0 }}>Conversations & Sessions</Typography.Title>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            All chat sessions, distillation data, and active session memory
          </Typography.Text>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={load} size="small">Refresh</Button>
          <ExportDropdown data={data} filename="conversations" />
        </Space>
      </div>

      {/* KPI Cards */}
      <Row gutter={[10, 10]} style={{ marginBottom: 12 }}>
        {[
          { title: 'Conversations', value: stats?.total_conversations ?? total, icon: <MessageOutlined />, color: '#3b82f6' },
          { title: 'Messages', value: stats?.total_messages ?? 0, icon: <ThunderboltOutlined />, color: '#8b5cf6' },
          { title: 'Unique Users', value: stats?.unique_users ?? 0, icon: <UserOutlined />, color: '#10b981' },
          { title: 'Avg Msgs/Conv', value: stats?.avg_messages_per_conversation ?? 0, icon: <BranchesOutlined />, color: '#f59e0b' },
          { title: 'Routing Decisions', value: stats?.total_routing_decisions ?? 0, icon: <RocketOutlined />, color: '#ec4899' },
          { title: 'Last 24h', value: stats?.recent_24h ?? 0, icon: <ClockCircleOutlined />, color: '#06b6d4' },
          { title: 'Distillation Samples', value: distSamples, icon: <ExperimentOutlined />, color: '#f59e0b' },
          { title: 'Active Sessions', value: sessions.length, icon: <SafetyCertificateOutlined />, color: '#10b981' },
        ].map((s) => (
          <Col key={s.title} xs={12} sm={6} md={3}>
            <Card size="small" hoverable>
              <Statistic title={s.title} value={s.value} prefix={s.icon} valueStyle={{ color: s.color, fontSize: 18 }} />
            </Card>
          </Col>
        ))}
      </Row>

      {/* Source Distribution + View Toggle */}
      <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
        <Col xs={24} md={8}>
          <Card title="Source Distribution" size="small">
            {sourcePie.length > 0 ? (
              <>
                <ResponsiveContainer width="100%" height={160}>
                  <PieChart>
                    <Pie data={sourcePie} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={55} innerRadius={25}>
                      {sourcePie.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                    </Pie>
                    <RTooltip />
                  </PieChart>
                </ResponsiveContainer>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                  {sourcePie.map((d, i) => {
                    const cfg = SOURCE_CONFIG[d.name];
                    return <Tag key={d.name} color={cfg?.color || COLORS[i % COLORS.length]} style={{ fontSize: 10 }}>{cfg?.label || d.name}: {d.value}</Tag>;
                  })}
                </div>
              </>
            ) : (
              <div style={{ height: 180, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column' }}>
                <MessageOutlined style={{ fontSize: 28, color: '#4b5563', marginBottom: 8 }} />
                <Typography.Text type="secondary" style={{ fontSize: 11 }}>No source data yet</Typography.Text>
              </div>
            )}
          </Card>
        </Col>
        <Col xs={24} md={16}>
          <Card size="small" title={
            <Space>
              <span>Data View</span>
              <Segmented options={[
                { label: 'Conversations', value: 'conversations', icon: <MessageOutlined /> },
                { label: 'Active Sessions', value: 'sessions', icon: <SafetyCertificateOutlined /> },
              ]} value={view} onChange={(v) => setView(v as any)} size="small" />
            </Space>
          }>
            {view === 'sessions' ? (
              sessions.length > 0 ? (
                <Table columns={sessionColumns} dataSource={sessions} rowKey="id" size="small" pagination={false} />
              ) : (
                <div style={{ textAlign: 'center', padding: 24 }}>
                  <SafetyCertificateOutlined style={{ fontSize: 28, color: '#4b5563', marginBottom: 8 }} />
                  <div><Typography.Text type="secondary" style={{ fontSize: 11 }}>No active sessions — sessions are created when using /atlas endpoint</Typography.Text></div>
                </div>
              )
            ) : (
              <div style={{ fontSize: 12, color: '#9ca3af' }}>
                <Row gutter={16}>
                  {Object.entries(stats?.sources || {}).map(([src, count]) => {
                    const cfg = SOURCE_CONFIG[src] || { label: src, color: 'default', icon: <BranchesOutlined /> };
                    return (
                      <Col key={src} span={8}>
                        <Card size="small" style={{ marginBottom: 8 }}>
                          <Space>
                            <Tag icon={cfg.icon} color={cfg.color}>{cfg.label}</Tag>
                            <Typography.Text strong>{count as number}</Typography.Text>
                          </Space>
                        </Card>
                      </Col>
                    );
                  })}
                </Row>
              </div>
            )}
          </Card>
        </Col>
      </Row>

      {/* Filters */}
      <Space style={{ marginBottom: 10 }} wrap>
        <Search placeholder="Search conversations..." allowClear prefix={<SearchOutlined />} onSearch={setSearch} style={{ width: 280 }} size="small" />
        <DateRangeFilter value={dateRange} onChange={setDateRange} />
      </Space>

      {/* Main Table */}
      <Card size="small" styles={{ body: { padding: 0 } }}>
        <Table
          columns={columns}
          dataSource={data}
          rowKey="id"
          loading={loading}
          pagination={pagination}
          size="small"
          locale={{
            emptyText: (
              <div style={{ padding: '32px 0', textAlign: 'center' }}>
                <MessageOutlined style={{ fontSize: 36, color: '#4b5563', marginBottom: 10 }} />
                <div><Typography.Text type="secondary" style={{ fontSize: 13 }}>No conversations yet</Typography.Text></div>
                <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                  Send requests to any <code>atlas-*</code> model via the API or Playground to start recording
                </Typography.Text>
              </div>
            ),
          }}
          onRow={(record) => ({
            onClick: () => navigate(`/conversations/${record.id}`),
            style: { cursor: 'pointer' },
          })}
        />
      </Card>
    </div>
  );
}
