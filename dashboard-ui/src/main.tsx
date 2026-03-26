import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { ConfigProvider, theme, App as AntApp } from 'antd';
import { useThemeStore } from './stores/themeStore';
import AppRoot from './App';
import './index.css';

function ThemeWrapper() {
  const isDark = useThemeStore((s) => s.isDark);

  const themeConfig = {
    algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm,
    token: {
      colorPrimary: '#3b82f6',
      borderRadius: 8,
      fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
      ...(isDark
        ? {
            colorBgContainer: '#111827',
            colorBgElevated: '#1f2937',
            colorBorder: '#374151',
            colorBgLayout: '#030712',
          }
        : {}),
    },
    components: {
      Layout: {
        siderBg: isDark ? '#0f172a' : '#fff',
        headerBg: isDark ? '#111827' : '#fff',
        bodyBg: isDark ? '#030712' : '#f5f5f5',
      },
      Menu: {
        darkItemBg: 'transparent',
        darkSubMenuItemBg: 'transparent',
      },
    },
  };

  return (
    <ConfigProvider theme={themeConfig}>
      <AntApp>
        <BrowserRouter>
          <AppRoot />
        </BrowserRouter>
      </AntApp>
    </ConfigProvider>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ThemeWrapper />
  </React.StrictMode>,
);
