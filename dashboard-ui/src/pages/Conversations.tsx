import { useEffect, useState } from 'react';
import { Typography, Table, Tag, Input, Space, Card } from 'antd';
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table';
import { useNavigate } from 'react-router-dom';
import { getConversations } from '../lib/api';
import ExportDropdown from '../components/shared/ExportDropdown';
import DateRangeFilter from '../components/shared/DateRangeFilter';
import dayjs from 'dayjs';

const { Search } = Input;

export default function Conversations() {
  const [data, setData] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [search, setSearch] = useState('');
  const [dateRange, setDateRange] = useState<[string | null, string | null]>([null, null]);
  const navigate = useNavigate();

  const load = () => {
    setLoading(true);
    getConversations({
      limit: pageSize,
      offset: (page - 1) * pageSize,
      search: search || undefined,
      date_from: dateRange[0] || undefined,
      date_to: dateRange[1] || undefined,
    })
      .then((res) => {
        setData(res.data || []);
        setTotal(res.total || 0);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(load, [page, pageSize, search, dateRange]);

  const columns: ColumnsType<any> = [
    {
      title: 'ID',
      dataIndex: 'id',
      width: 120,
      render: (id: string) => (
        <a onClick={() => navigate(`/conversations/${id}`)} style={{ fontFamily: 'monospace', fontSize: 12 }}>
          {id.slice(0, 8)}...
        </a>
      ),
    },
    {
      title: 'Source',
      dataIndex: 'source',
      width: 130,
      render: (s: string) => <Tag color="purple">{s}</Tag>,
      filters: [
        { text: 'proxy', value: 'proxy' },
        { text: 'import:paperclip', value: 'import:paperclip' },
        { text: 'import:openai_jsonl', value: 'import:openai_jsonl' },
      ],
      onFilter: (value, record) => record.source === value,
    },
    {
      title: 'User',
      dataIndex: 'user_id',
      render: (u: string | null) => u || '—',
    },
    {
      title: 'Messages',
      dataIndex: 'message_count',
      width: 100,
      sorter: (a, b) => a.message_count - b.message_count,
    },
    {
      title: 'Created',
      dataIndex: 'created_at',
      width: 180,
      sorter: (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
      render: (d: string) => d ? dayjs(d).format('YYYY-MM-DD HH:mm') : '—',
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
        <Typography.Title level={4} style={{ margin: 0 }}>Conversations</Typography.Title>
        <ExportDropdown data={data} filename="conversations" />
      </div>

      <Space style={{ marginBottom: 16 }} wrap>
        <Search
          placeholder="Search conversations..."
          allowClear
          onSearch={setSearch}
          style={{ width: 300 }}
        />
        <DateRangeFilter value={dateRange} onChange={setDateRange} />
      </Space>

      <Card size="small" styles={{ body: { padding: 0 } }}>
        <Table
          columns={columns}
          dataSource={data}
          rowKey="id"
          loading={loading}
          pagination={pagination}
          size="small"
          onRow={(record) => ({
            onClick: () => navigate(`/conversations/${record.id}`),
            style: { cursor: 'pointer' },
          })}
        />
      </Card>
    </div>
  );
}
