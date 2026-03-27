import { useEffect, useState } from 'react';
import { Typography, Table, Tag, Input, Space, Card, Row, Col, Statistic, Badge, Button, App } from 'antd';
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table';
import {
  MessageOutlined, UserOutlined, ClockCircleOutlined, ThunderboltOutlined,
  CloudServerOutlined, SearchOutlined, ReloadOutlined, RocketOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { getConversations, getOverview } from '../lib/api';
import ExportDropdown from '../components/shared/ExportDropdown';
import DateRangeFilter from '../components/shared/DateRangeFilter';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
dayjs.extend(relativeTime);

const { Search } = Input;

const SOURCE_COLORS: Record<string, string> = {
  proxy: 'blue',
  'import:paperclip': 'purple',
  'import:openai_jsonl': 'orange',
  openclaw: 'cyan',
  distillation: 'gold',
};

export default function Conversations() {
  const [data, setData] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [overview, setOverview] = useState<any>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [search, setSearch] = useState('');
  const [dateRange, setDateRange] = useState<[string | null, string | null]>([null, null]);
  const navigate = useNavigate();

  const load = () => {
    setLoading(true);
    Promise.all([
      getConversations({
        limit: pageSize,
        offset: (page - 1) * pageSize,
        search: search || undefined,
        date_from: dateRange[0] || undefined,
        date_to: dateRange[1] || undefined,
      }),
      getOverview(),
    ])
      .then(([res, ov]) => {
        setData(res.data || []);
        setTotal(res.total || 0);
        setOverview(ov);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(load, [page, pageSize, search, dateRange]);

  const m = overview?.metrics;
  const totalMessages = data.reduce((sum: number, c: any) => sum + (c.message_count || 0), 0);
  const sources = data.reduce((acc: Record<string, number>, c: any) => {
    acc[c.source] = (acc[c.source] || 0) + 1;
    return acc;
  }, {});

  const columns: ColumnsType<any> = [
    {
      title: 'ID',
      dataIndex: 'id',
      width: 100,
      render: (id: string) => (
        <a onClick={() => navigate(`/conversations/${id}`)} style={{ fontFamily: 'monospace', fontSize: 11 }}>
          {id.slice(0, 8)}
        </a>
      ),
    },
    {
      title: 'Source',
      dataIndex: 'source',
      width: 130,
      render: (s: string) => (
        <Tag color={SOURCE_COLORS[s] || 'default'} style={{ fontSize: 11 }}>
          {s === 'proxy' ? '⚡ Proxy' : s === 'openclaw' ? '🦞 OpenClaw' : s}
        </Tag>
      ),
      filters: [
        { text: '⚡ Proxy', value: 'proxy' },
        { text: '🦞 OpenClaw', value: 'openclaw' },
        { text: '📎 Paperclip', value: 'import:paperclip' },
        { text: '📄 JSONL', value: 'import:openai_jsonl' },
      ],
      onFilter: (value, record) => record.source === value,
    },
    {
      title: 'User',
      dataIndex: 'user_id',
      width: 140,
      render: (u: string | null) => u ? (
        <Space size={4}>
          <UserOutlined style={{ fontSize: 11, color: '#6b7280' }} />
          <span style={{ fontSize: 12 }}>{u}</span>
        </Space>
      ) : <span style={{ color: '#4b5563' }}>—</span>,
    },
    {
      title: 'Messages',
      dataIndex: 'message_count',
      width: 90,
      sorter: (a, b) => a.message_count - b.message_count,
      render: (c: number) => (
        <Badge count={c} showZero color={c > 5 ? '#3b82f6' : '#6b7280'}
          style={{ fontSize: 11 }} overflowCount={999} />
      ),
    },
    {
      title: 'Preview',
      dataIndex: 'metadata',
      ellipsis: true,
      render: (_: any, record: any) => (
        <Typography.Text type="secondary" style={{ fontSize: 11 }} ellipsis>
          {record.metadata?.preview || record.metadata?.openclaw_id || '—'}
        </Typography.Text>
      ),
    },
    {
      title: 'Created',
      dataIndex: 'created_at',
      width: 160,
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

  const pagination: TablePaginationConfig = {
    current: page,
    pageSize,
    total,
    showSizeChanger: true,
    showTotal: (t) => `${t} conversations`,
    pageSizeOptions: [10, 25, 50, 100],
    onChange: (p, ps) => { setPage(p); setPageSize(ps); },
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div>
          <Typography.Title level={4} style={{ margin: 0 }}>Conversations</Typography.Title>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            All chat sessions from proxy, imports, and distillation
          </Typography.Text>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={load} size="small">Refresh</Button>
          <ExportDropdown data={data} filename="conversations" />
        </Space>
      </div>

      {/* KPI Cards */}
      <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="Total Conversations" value={total} prefix={<MessageOutlined />} valueStyle={{ color: '#3b82f6' }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="Total Messages" value={totalMessages || m?.total_prompt_tokens ? '~' + (m?.request_count * 2 || 0) : 0}
              prefix={<ThunderboltOutlined />} valueStyle={{ color: '#8b5cf6' }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="Total Requests" value={m?.request_count ?? 0}
              prefix={<RocketOutlined />} valueStyle={{ color: '#10b981' }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <div style={{ fontSize: 12, color: '#9ca3af', marginBottom: 4 }}>Sources</div>
            <Space wrap size={4}>
              {Object.entries(sources).map(([src, count]) => (
                <Tag key={src} color={SOURCE_COLORS[src] || 'default'} style={{ fontSize: 10 }}>
                  {src}: {count as number}
                </Tag>
              ))}
              {Object.keys(sources).length === 0 && <Typography.Text type="secondary" style={{ fontSize: 11 }}>No data yet</Typography.Text>}
            </Space>
          </Card>
        </Col>
      </Row>

      {/* Filters */}
      <Space style={{ marginBottom: 12 }} wrap>
        <Search
          placeholder="Search conversations..."
          allowClear
          prefix={<SearchOutlined />}
          onSearch={setSearch}
          style={{ width: 300 }}
        />
        <DateRangeFilter value={dateRange} onChange={setDateRange} />
      </Space>

      {/* Table */}
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
              <div style={{ padding: '40px 0', textAlign: 'center' }}>
                <MessageOutlined style={{ fontSize: 40, color: '#4b5563', marginBottom: 12 }} />
                <div>
                  <Typography.Text type="secondary" style={{ fontSize: 14 }}>No conversations yet</Typography.Text>
                </div>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  Send requests to <code>alpheric-1</code> via the API or Playground to start recording conversations
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
