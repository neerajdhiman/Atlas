import { Navigate } from 'react-router-dom';
import { useAuthStore } from '../../stores/authStore';

interface Props {
  children: React.ReactNode;
}

export default function ProtectedRoute({ children }: Props) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  // If no auth configured (dev mode), allow access
  // In production, the backend will return 401 for unauthenticated requests
  if (!isAuthenticated && localStorage.getItem('a1-auth-required') === 'true') {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
