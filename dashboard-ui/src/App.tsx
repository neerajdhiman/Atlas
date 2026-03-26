import { Routes, Route, NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  MessageSquare,
  GitBranch,
  Server,
  Brain,
  BarChart3,
  Download,
  Settings,
  Zap,
} from 'lucide-react';
import Overview from './pages/Overview';
import Conversations from './pages/Conversations';
import ConversationDetail from './pages/ConversationDetail';
import Routing from './pages/Routing';
import Providers from './pages/Providers';
import Training from './pages/Training';
import Analytics from './pages/Analytics';
import Import from './pages/Import';
import SettingsPage from './pages/Settings';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Overview' },
  { to: '/conversations', icon: MessageSquare, label: 'Conversations' },
  { to: '/routing', icon: GitBranch, label: 'Routing' },
  { to: '/providers', icon: Server, label: 'Providers' },
  { to: '/training', icon: Brain, label: 'Training' },
  { to: '/analytics', icon: BarChart3, label: 'Analytics' },
  { to: '/import', icon: Download, label: 'Import' },
  { to: '/settings', icon: Settings, label: 'Settings' },
];

export default function App() {
  return (
    <div className="flex h-screen">
      {/* Sidebar */}
      <aside className="w-60 bg-gray-900 border-r border-gray-800 flex flex-col">
        <div className="p-4 border-b border-gray-800">
          <div className="flex items-center gap-2">
            <Zap className="w-6 h-6 text-blue-500" />
            <span className="text-lg font-bold">A1 Trainer</span>
          </div>
          <p className="text-xs text-gray-500 mt-1">OneDesk AI Middleware</p>
        </div>
        <nav className="flex-1 p-3 space-y-1">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `sidebar-link ${isActive ? 'active' : ''}`
              }
            >
              <Icon className="w-4 h-4" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="p-4 border-t border-gray-800">
          <p className="text-xs text-gray-600">v0.1.0</p>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto p-6">
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/conversations" element={<Conversations />} />
          <Route path="/conversations/:id" element={<ConversationDetail />} />
          <Route path="/routing" element={<Routing />} />
          <Route path="/providers" element={<Providers />} />
          <Route path="/training" element={<Training />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/import" element={<Import />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>
    </div>
  );
}
