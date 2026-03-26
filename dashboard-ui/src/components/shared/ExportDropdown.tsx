import { Dropdown, Button } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import { exportCSV, exportJSON } from '../../lib/export';

interface Props {
  data: Record<string, any>[];
  filename: string;
}

export default function ExportDropdown({ data, filename }: Props) {
  const items = [
    {
      key: 'csv',
      label: 'Export CSV',
      onClick: () => exportCSV(data, filename),
    },
    {
      key: 'json',
      label: 'Export JSON',
      onClick: () => exportJSON(data, filename),
    },
  ];

  return (
    <Dropdown menu={{ items }} trigger={['click']}>
      <Button icon={<DownloadOutlined />}>Export</Button>
    </Dropdown>
  );
}
