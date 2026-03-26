import { Skeleton, Card, Row, Col, Space } from 'antd';

interface Props {
  type?: 'cards' | 'table' | 'detail' | 'form';
}

export default function PageSkeleton({ type = 'cards' }: Props) {
  if (type === 'table') {
    return (
      <div>
        <Skeleton.Input active style={{ width: 300, marginBottom: 16 }} />
        <Card>
          <Skeleton active paragraph={{ rows: 8 }} />
        </Card>
      </div>
    );
  }

  if (type === 'detail') {
    return (
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Card><Skeleton active paragraph={{ rows: 2 }} /></Card>
        <Card><Skeleton active paragraph={{ rows: 4 }} /></Card>
        <Card><Skeleton active paragraph={{ rows: 4 }} /></Card>
      </Space>
    );
  }

  if (type === 'form') {
    return (
      <Card style={{ maxWidth: 600 }}>
        <Skeleton active paragraph={{ rows: 6 }} />
      </Card>
    );
  }

  // cards (default)
  return (
    <div>
      <Skeleton.Input active style={{ width: 200, marginBottom: 24 }} />
      <Row gutter={[16, 16]}>
        {Array.from({ length: 7 }).map((_, i) => (
          <Col key={i} xs={12} sm={8} md={6} lg={3}>
            <Card><Skeleton active paragraph={{ rows: 1 }} /></Card>
          </Col>
        ))}
      </Row>
      <Row gutter={[16, 16]} style={{ marginTop: 24 }}>
        {Array.from({ length: 3 }).map((_, i) => (
          <Col key={i} xs={24} lg={8}>
            <Card><Skeleton active paragraph={{ rows: 6 }} /></Card>
          </Col>
        ))}
      </Row>
    </div>
  );
}
