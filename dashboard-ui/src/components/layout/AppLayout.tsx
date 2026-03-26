import { useState } from 'react';
import { Layout, Drawer, Button } from 'antd';
import { MenuOutlined } from '@ant-design/icons';
import Sidebar from './Sidebar';
import HeaderBar from './HeaderBar';

const { Sider, Content } = Layout;

interface Props {
  children: React.ReactNode;
}

export default function AppLayout({ children }: Props) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <Layout style={{ minHeight: '100vh' }}>
      {/* Desktop sidebar */}
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        breakpoint="lg"
        collapsedWidth={64}
        trigger={null}
        width={240}
        style={{
          overflow: 'auto',
          height: '100vh',
          position: 'fixed',
          left: 0,
          top: 0,
          bottom: 0,
          zIndex: 100,
        }}
        className="hidden-mobile"
      >
        <Sidebar />
      </Sider>

      {/* Mobile drawer */}
      <Drawer
        placement="left"
        onClose={() => setMobileOpen(false)}
        open={mobileOpen}
        width={240}
        styles={{ body: { padding: 0 } }}
        className="visible-mobile"
      >
        <Sidebar />
      </Drawer>

      <Layout style={{ marginLeft: collapsed ? 64 : 240, transition: 'margin-left 0.2s' }}>
        <HeaderBar />
        <Content style={{ padding: 24, minHeight: 'calc(100vh - 56px)', overflow: 'auto' }}>
          {/* Mobile menu button */}
          <Button
            className="visible-mobile-only"
            icon={<MenuOutlined />}
            onClick={() => setMobileOpen(true)}
            style={{ marginBottom: 16, display: 'none' }}
          />
          {children}
        </Content>
      </Layout>
    </Layout>
  );
}
