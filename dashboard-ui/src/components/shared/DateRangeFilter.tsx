import { DatePicker, Space } from 'antd';
import dayjs, { Dayjs } from 'dayjs';

const { RangePicker } = DatePicker;

interface Props {
  value?: [string | null, string | null];
  onChange: (dates: [string | null, string | null]) => void;
}

const presets: { label: string; value: [Dayjs, Dayjs] }[] = [
  { label: 'Today', value: [dayjs().startOf('day'), dayjs().endOf('day')] },
  { label: 'Last 7 days', value: [dayjs().subtract(7, 'day'), dayjs()] },
  { label: 'Last 30 days', value: [dayjs().subtract(30, 'day'), dayjs()] },
  { label: 'Last 90 days', value: [dayjs().subtract(90, 'day'), dayjs()] },
];

export default function DateRangeFilter({ value, onChange }: Props) {
  const dayjsValue: [Dayjs | null, Dayjs | null] | undefined =
    value?.[0] && value?.[1] ? [dayjs(value[0]), dayjs(value[1])] : undefined;

  return (
    <Space>
      <RangePicker
        value={dayjsValue}
        presets={presets}
        onChange={(dates) => {
          if (dates && dates[0] && dates[1]) {
            onChange([dates[0].toISOString(), dates[1].toISOString()]);
          } else {
            onChange([null, null]);
          }
        }}
        allowClear
        size="middle"
      />
    </Space>
  );
}
