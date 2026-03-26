import { Drawer, List, Badge, Button, Empty, Tag, Typography } from 'antd';
import { CheckOutlined, DeleteOutlined } from '@ant-design/icons';
import { useNotificationStore } from '../../stores/notificationStore';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';

dayjs.extend(relativeTime);

const { Text } = Typography;

interface Props {
  open: boolean;
  onClose: () => void;
}

const typeColor = {
  info: 'blue',
  success: 'green',
  warning: 'orange',
  error: 'red',
};

export default function NotificationCenter({ open, onClose }: Props) {
  const { notifications, markRead, markAllRead, clear } = useNotificationStore();

  return (
    <Drawer
      title="Notifications"
      placement="right"
      onClose={onClose}
      open={open}
      width={380}
      extra={
        notifications.length > 0 && (
          <>
            <Button size="small" icon={<CheckOutlined />} onClick={markAllRead} style={{ marginRight: 8 }}>
              Mark all read
            </Button>
            <Button size="small" icon={<DeleteOutlined />} onClick={clear} danger>
              Clear
            </Button>
          </>
        )
      }
    >
      {notifications.length === 0 ? (
        <Empty description="No notifications" />
      ) : (
        <List
          dataSource={notifications}
          renderItem={(n) => (
            <List.Item
              onClick={() => markRead(n.id)}
              style={{
                cursor: 'pointer',
                opacity: n.read ? 0.6 : 1,
                background: n.read ? 'transparent' : 'rgba(59,130,246,0.05)',
                padding: '12px 8px',
                borderRadius: 6,
              }}
            >
              <List.Item.Meta
                title={
                  <span>
                    <Tag color={typeColor[n.type]} style={{ marginRight: 8 }}>{n.type}</Tag>
                    {n.title}
                    {!n.read && <Badge dot style={{ marginLeft: 6 }} />}
                  </span>
                }
                description={
                  <>
                    <Text type="secondary" style={{ fontSize: 12 }}>{n.message}</Text>
                    <br />
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {dayjs(n.timestamp).fromNow()}
                    </Text>
                  </>
                }
              />
            </List.Item>
          )}
        />
      )}
    </Drawer>
  );
}
