import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useEffect } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { AppShell } from './components/layout/AppShell';
import { LoginPage } from './pages/auth/LoginPage';
import { RegisterPage } from './pages/auth/RegisterPage';
import { DashboardPage } from './pages/dashboard/DashboardPage';
import { FinancePage } from './pages/finance/FinancePage';
import { HRPage } from './pages/hr/HRPage';
import { ProjectsPage } from './pages/projects/ProjectsPage';
import { InventoryPage } from './pages/inventory/InventoryPage';
import { CodingPage } from './pages/coding/CodingPage';
import { ModulePage } from './pages/ModulePage';
import { SearchPage } from './pages/search/SearchPage';
import { SettingsPage } from './pages/settings/SettingsPage';
import { useAuthStore } from './store/auth';
import { useThemeStore } from './store/theme';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
});

function Protected({ children }: { children: JSX.Element }) {
  const { user, initialized, loading, loadMe } = useAuthStore();
  const location = useLocation();

  useEffect(() => {
    if (!initialized) loadMe();
  }, [initialized, loadMe]);

  if (loading || !initialized) {
    return (
      <div className="grid min-h-screen place-items-center bg-surface text-ink">
        <p className="text-sm text-ink-muted">Loading EnterpriseCore…</p>
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />;
  return children;
}

function PublicOnly({ children }: { children: JSX.Element }) {
  const { user, initialized, loadMe } = useAuthStore();
  useEffect(() => {
    if (!initialized) loadMe();
  }, [initialized, loadMe]);
  if (user) return <Navigate to="/" replace />;
  return children;
}

export function App() {
  const apply = useThemeStore((s) => s.apply);
  useEffect(() => {
    apply();
  }, [apply]);

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<PublicOnly><LoginPage /></PublicOnly>} />
          <Route path="/register" element={<PublicOnly><RegisterPage /></PublicOnly>} />
          <Route path="/" element={<Protected><AppShell /></Protected>}>
            <Route index element={<DashboardPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="search" element={<SearchPage />} />
            <Route path="finance" element={<FinancePage />} />
            <Route path="hr" element={<HRPage />} />
            <Route path="projects" element={<ProjectsPage />} />
            <Route path="inventory" element={<InventoryPage />} />
            <Route path="coding" element={<CodingPage />} />
            <Route path=":module" element={<ModulePage />} />
          </Route>
        </Routes>
      </BrowserRouter>
      <Toaster
        position="top-right"
        toastOptions={{
          className: 'text-sm',
          style: { background: 'rgb(var(--color-surface-elevated))', color: 'rgb(var(--color-ink))', border: '1px solid rgb(var(--color-border))' },
        }}
      />
    </QueryClientProvider>
  );
}
