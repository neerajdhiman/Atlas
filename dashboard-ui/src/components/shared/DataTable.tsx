import { useState } from 'react';
import { Table, Input, Space } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';

interface DataTableProps<T = any> {
  columns: ColumnsType<T>;
  dataSource: T[];
  loading?: boolean;
  /** Placeholder shown in the search box. Omit to hide search entirely. */
  searchPlaceholder?: string;
  /** Record keys to match against the search query. Pass [] to disable search. */
  searchKeys?: (keyof T)[];
  rowKey?: string | ((record: T) => string);
  pageSize?: number;
  size?: 'small' | 'middle' | 'large';
  style?: React.CSSProperties;
}

/**
 * Table + search bar combo used across the dashboard.
 * Client-side filtering on `searchKeys`; delegates pagination to Ant Design Table.
 */
export default function DataTable<T extends object = any>({
  columns,
  dataSource,
  loading,
  searchPlaceholder = 'Search…',
  searchKeys = [],
  rowKey = 'id',
  pageSize = 10,
  size = 'small',
  style,
}: DataTableProps<T>) {
  const [search, setSearch] = useState('');

  const filtered =
    search && searchKeys.length
      ? dataSource.filter((row) =>
          searchKeys.some((key) =>
            String((row as any)[key] ?? '')
              .toLowerCase()
              .includes(search.toLowerCase()),
          ),
        )
      : dataSource;

  return (
    <Space direction="vertical" style={{ width: '100%', ...style }}>
      {searchKeys.length > 0 && (
        <Input
          prefix={<SearchOutlined />}
          placeholder={searchPlaceholder}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          allowClear
          style={{ maxWidth: 320 }}
        />
      )}
      <Table
        columns={columns}
        dataSource={filtered}
        loading={loading}
        rowKey={rowKey as string}
        size={size}
        pagination={{ pageSize, showSizeChanger: false }}
      />
    </Space>
  );
}
