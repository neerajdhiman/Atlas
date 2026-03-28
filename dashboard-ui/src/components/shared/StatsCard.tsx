import { Card, Statistic } from 'antd';
import type { CSSProperties, ReactNode } from 'react';

interface StatsCardProps {
  title: string;
  value: string | number;
  /** Shown as the Statistic prefix (left of value). Pass an icon node here. */
  icon?: ReactNode;
  suffix?: string;
  precision?: number;
  color?: string;
  style?: CSSProperties;
  hoverable?: boolean;
}

/**
 * Lightweight Card + Statistic wrapper used across the dashboard.
 * Reduces Card/Statistic boilerplate in list renders.
 */
export default function StatsCard({
  title,
  value,
  icon,
  suffix,
  precision,
  color,
  style,
  hoverable = true,
}: StatsCardProps) {
  return (
    <Card size="small" hoverable={hoverable} style={style}>
      <Statistic
        title={title}
        value={value}
        prefix={icon}
        suffix={suffix}
        precision={precision}
        valueStyle={color ? { color } : undefined}
      />
    </Card>
  );
}
