import { useState } from 'react';
import { Layout, Switch, Badge, Avatar, Dropdown, Space, Breadcrumb, Tooltip } from 'antd';
import {
  BellOutlined,
  UserOutlined,
  LogoutOutlined,
  SunOutlined,
  MoonOutlined,
} from '@ant-design/icons';
import { useLocation, Link } from 'react-router-dom';
import { useThemeStore } from '../../stores/themeStore';
import { useAuthStore } from '../../stores/authStore';
import { useNotificationStore } from '../../stores/notificationStore';
import NotificationCenter from '../shared/NotificationCenter';

const { Header } = Layout;

const pathLabels: Record<string, string> = {
  '': 'Overview',
  conversations: 'Conversations',
  routing: 'Routing',
  providers: 'Providers',
  training: 'Training',
  analytics: 'Analytics',
  import: 'Import',
  settings: 'Settings',
  login: 'Login',
};

export default function HeaderBar() {
  const { isDark, toggle } = useThemeStore();
  const { user, logout } = useAuthStore();
  const unreadCount = useNotificationStore((s) => s.unreadCount);
  const [notifOpen, setNotifOpen] = useState(false);
  const location = useLocation();

  const pathParts = location.pathname.split('/').filter(Boolean);
  const breadcrumbItems = [
    { title: <Link to="/">Home</Link> },
    ...pathParts.map((part, i) => ({
      title: i === pathParts.length - 1
        ? (pathLabels[part] || part)
        : <Link to={`/${pathParts.slice(0, i + 1).join('/')}`}>{pathLabels[part] || part}</Link>,
    })),
  ];

  const userMenuItems = [
    {
      key: 'profile',
      icon: <UserOutlined />,
      label: user ? `${user.username} (${user.role})` : 'Not logged in',
      disabled: true,
    },
    { type: 'divider' as const },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: 'Logout',
      danger: true,
      onClick: logout,
    },
  ];

  return (
    <>
      <Header
        style={{
          padding: '0 24px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          height: 56,
          lineHeight: '56px',
        }}
      >
        <Breadcrumb items={breadcrumbItems} />

        <Space size="middle">
          <Tooltip title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}>
            <Switch
              checked={isDark}
              onChange={toggle}
              checkedChildren={<MoonOutlined />}
              unCheckedChildren={<SunOutlined />}
              size="small"
            />
          </Tooltip>

          <Tooltip title="Notifications">
            <Badge count={unreadCount} size="small">
              <BellOutlined
                style={{ fontSize: 18, cursor: 'pointer' }}
                onClick={() => setNotifOpen(true)}
              />
            </Badge>
          </Tooltip>

          {user && (
            <Dropdown menu={{ items: userMenuItems }} trigger={['click']}>
              <Avatar
                size="small"
                icon={<UserOutlined />}
                style={{ cursor: 'pointer', background: '#3b82f6' }}
              />
            </Dropdown>
          )}
        </Space>
      </Header>

      <NotificationCenter open={notifOpen} onClose={() => setNotifOpen(false)} />
    </>
  );
}
