import { useEffect, useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useThemeStore } from '../../store/theme';
import { useOnline } from '../../hooks/useOnline';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';

export function AppShell() {
  const apply = useThemeStore((s) => s.apply);
  const online = useOnline();
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    apply();
  }, [apply]);

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  function openSearch() {
    navigate('/search');
  }

  return (
    <div className="flex min-h-screen bg-surface text-ink">
      <Sidebar mobileOpen={mobileOpen} onCloseMobile={() => setMobileOpen(false)} />
      <main className="flex min-w-0 flex-1 flex-col">
        <TopBar
          online={online}
          onOpenMobileSidebar={() => setMobileOpen(true)}
          onOpenSearch={openSearch}
        />
        <div className="flex-1 overflow-auto px-4 pb-8 pt-4 lg:px-8 lg:pt-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
