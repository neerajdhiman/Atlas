import { useState } from 'react';
import { Dropdown, Button, App } from 'antd';
import { DownloadOutlined, LoadingOutlined } from '@ant-design/icons';
import { exportCSV, exportJSON } from '../../lib/export';

interface Props {
  data: Record<string, any>[];
  filename: string;
  /** When provided, adds "Export All" items that call this before exporting */
  fetchAll?: () => Promise<Record<string, any>[]>;
}

export default function ExportDropdown({ data, filename, fetchAll }: Props) {
  const [exporting, setExporting] = useState(false);
  const { message: msg } = App.useApp();

  const handleExportAll = async (format: 'csv' | 'json') => {
    if (!fetchAll) return;
    setExporting(true);
    try {
      const all = await fetchAll();
      if (format === 'csv') exportCSV(all, filename);
      else exportJSON(all, filename);
    } catch {
      msg.error('Export failed');
    } finally {
      setExporting(false);
    }
  };

  const items = [
    {
      key: 'csv',
      label: fetchAll ? 'Export Page (CSV)' : 'Export CSV',
      onClick: () => exportCSV(data, filename),
    },
    {
      key: 'json',
      label: fetchAll ? 'Export Page (JSON)' : 'Export JSON',
      onClick: () => exportJSON(data, filename),
    },
    ...(fetchAll
      ? [
          { type: 'divider' as const },
          { key: 'all-csv', label: 'Export All (CSV)', onClick: () => handleExportAll('csv') },
          { key: 'all-json', label: 'Export All (JSON)', onClick: () => handleExportAll('json') },
        ]
      : []),
  ];

  return (
    <Dropdown menu={{ items }} trigger={['click']} disabled={exporting}>
      <Button icon={exporting ? <LoadingOutlined /> : <DownloadOutlined />} size="small">
        Export
      </Button>
    </Dropdown>
  );
}
