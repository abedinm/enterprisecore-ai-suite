import { useEffect, useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useThemeStore } from '../../store/theme';
import { useOnline } from '../../hooks/useOnline';
import { useLicenseFeatures } from '../../hooks/useLicenseFeatures';
import { useRealtimeNotifications } from '../../hooks/useRealtimeNotifications';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { OfflineBanner } from '../OfflineBanner';
import { RealtimeStatus } from '../RealtimeStatus';
import { UpdateAvailableBanner } from '../UpdateAvailableBanner';
import { CommandPalette } from '../CommandPalette';
import { PageTransition } from '../PageTransition';
import { FirstRunTour } from '../FirstRunTour';
import { QuickActionFab } from '../QuickActionFab';
import { ConfirmDialogHost } from '../ConfirmDialog';
import { AchievementCelebration } from '../gamification/AchievementCelebration';
import { useGamification } from '../../store/gamification';
import { useEasterEggs } from '../../hooks/useEasterEggs';

export function AppShell() {
  const apply = useThemeStore((s) => s.apply);
  const online = useOnline();
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  // Pre-fetch the license features so nav, route guards, and module pages
  // can gate themselves from the shared TanStack Query cache.
  useLicenseFeatures();
  // Mounts the realtime notifications channel once per session and
  // surfaces server events as toasts. The hook gates itself on auth
  // token presence so logged-out renders don't churn reconnects.
  useRealtimeNotifications();
  // Easter eggs — Konami code, 7-click logo.
  useEasterEggs();
  // Gamification — initial fetch + periodic refresh so newly-unlocked
  // achievements show their celebration even if the SPA didn't trigger them
  // (e.g. another user in the tenant fired the event).
  const fetchGam = useGamification(s => s.fetch);
  const refreshGam = useGamification(s => s.refresh);
  useEffect(() => {
    fetchGam();
    const t = window.setInterval(() => refreshGam(), 30_000);
    return () => window.clearInterval(t);
  }, [fetchGam, refreshGam]);

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
    <div className="relative flex min-h-screen bg-surface text-ink">
      {/* Ambient layer — soft animated gradient or grid, behind everything.
          Toggled / styled by `<html data-ambient>` from the theme store. */}
      <div className="ec-ambient" aria-hidden="true" />
      {/* WCAG 2.4.1 — first focusable element jumps past the sidebar/topbar
       * so keyboard users don't tab through 30+ nav links every page. */}
      <a href="#main-content" className="skip-link">Skip to content</a>
      <Sidebar mobileOpen={mobileOpen} onCloseMobile={() => setMobileOpen(false)} />
      <div className="relative flex min-w-0 flex-1 flex-col">
        <OfflineBanner />
        <TopBar
          online={online}
          onOpenMobileSidebar={() => setMobileOpen(true)}
          onOpenSearch={openSearch}
        />
        {/* Floating realtime pill — anchored top-right, doesn't push layout. */}
        <div className="pointer-events-none absolute right-4 top-2 z-30 hidden lg:block">
          <RealtimeStatus className="pointer-events-auto" />
        </div>
        <main
          id="main-content"
          tabIndex={-1}
          className="flex-1 overflow-auto px-4 pb-8 pt-4 lg:px-8 lg:pt-6 focus:outline-none"
        >
          <PageTransition>
            <Outlet />
          </PageTransition>
        </main>
      </div>
      <UpdateAvailableBanner />
      <CommandPalette />
      <AchievementCelebration />
      <FirstRunTour />
      <QuickActionFab />
      <ConfirmDialogHost />
    </div>
  );
}
