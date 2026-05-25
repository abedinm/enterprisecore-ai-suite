import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MotionConfig } from 'framer-motion';
import { Suspense, lazy, useEffect } from 'react';
import {
  BrowserRouter,
  HashRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
} from 'react-router-dom';

/**
 * Router selection
 * ----------------
 * The packaged Electron build runs from a ``file://`` origin; BrowserRouter
 * cannot serve clean URLs there (the OS doesn't know how to follow them).
 * The hosted web/SaaS build runs from ``https://app.example.com`` and very
 * much DOES want clean URLs (SEO, shareable links, server-side
 * back-button navigation).
 *
 * We pick at runtime:
 *   - file:// or Electron preload signal → HashRouter
 *   - everything else                    → BrowserRouter
 *
 * Operators can force-pin with VITE_FORCE_ROUTER=hash|browser at build time.
 */
const _forced = (import.meta.env.VITE_FORCE_ROUTER ?? '').toLowerCase();
const _isElectron =
  typeof window !== 'undefined' &&
  (Boolean((window as any).electron?.isElectron) || window.location.protocol === 'file:');
const Router: typeof BrowserRouter =
  _forced === 'hash' || (_forced !== 'browser' && _isElectron) ? HashRouter : BrowserRouter;
import { Toaster } from 'react-hot-toast';
import { ErrorBoundary } from './components/ErrorBoundary';
import { AppShell } from './components/layout/AppShell';
import { LoginPage } from './pages/auth/LoginPage';
import { RegisterPage } from './pages/auth/RegisterPage';
import { DashboardPage } from './pages/dashboard/DashboardPage';

const SignupPage = lazy(() => import('./pages/auth/SignupPage').then(m => ({ default: m.SignupPage })));
const MagicLinkPage = lazy(() => import('./pages/auth/MagicLinkPage').then(m => ({ default: m.MagicLinkPage })));
const ConsumeLinkPage = lazy(() => import('./pages/auth/ConsumeLinkPage').then(m => ({ default: m.ConsumeLinkPage })));
const AcceptInvitePage = lazy(() => import('./pages/auth/AcceptInvitePage').then(m => ({ default: m.AcceptInvitePage })));

const OrgLayout = lazy(() => import('./pages/org/OrgLayout').then(m => ({ default: m.OrgLayout })));
const OrgGeneralTab = lazy(() => import('./pages/org/GeneralTab').then(m => ({ default: m.GeneralTab })));
const OrgUsersTab = lazy(() => import('./pages/org/UsersTab').then(m => ({ default: m.UsersTab })));
const OrgBillingTab = lazy(() => import('./pages/org/BillingTab').then(m => ({ default: m.BillingTab })));
const OrgSSOTab = lazy(() => import('./pages/org/SSOTab').then(m => ({ default: m.SSOTab })));
const OrgSCIMTab = lazy(() => import('./pages/org/SCIMTab').then(m => ({ default: m.SCIMTab })));
const OrgRolesTab = lazy(() => import('./pages/org/RolesTab').then(m => ({ default: m.RolesTab })));
const OrgEncryptionTab = lazy(() => import('./pages/org/EncryptionTab').then(m => ({ default: m.EncryptionTab })));
const OrgSecurityTab = lazy(() => import('./pages/org/SecurityTab').then(m => ({ default: m.SecurityTab })));
const OrgWebhooksTab = lazy(() => import('./pages/org/WebhooksTab').then(m => ({ default: m.WebhooksTab })));
const OrgPrivacyTab = lazy(() => import('./pages/org/PrivacyTab').then(m => ({ default: m.PrivacyTab })));
const OrgUsageTab = lazy(() => import('./pages/org/UsageTab').then(m => ({ default: m.UsageTab })));
import { useAuthStore } from './store/auth';
import { useThemeStore } from './store/theme';

// Lazy-loaded modules — heavy imports (Monaco, xterm, Recharts, etc.) load only
// when the route is actually visited. Eager-loaded routes above are the
// always-shown shells (login, dashboard).
const FinancePage = lazy(() => import('./pages/finance/FinancePage').then(m => ({ default: m.FinancePage })));
const HRPage = lazy(() => import('./pages/hr/HRPage').then(m => ({ default: m.HRPage })));
const CRMPage = lazy(() => import('./pages/crm/CRMPage').then(m => ({ default: m.CRMPage })));
const ProjectsPage = lazy(() => import('./pages/projects/ProjectsPage').then(m => ({ default: m.ProjectsPage })));
const InventoryPage = lazy(() => import('./pages/inventory/InventoryPage').then(m => ({ default: m.InventoryPage })));
const CodingPage = lazy(() => import('./pages/coding/CodingPage').then(m => ({ default: m.CodingPage })));
const AIBrainPage = lazy(() => import('./pages/ai/AIBrainPage').then(m => ({ default: m.AIBrainPage })));
const DocumentsPage = lazy(() => import('./pages/documents/DocumentsPage').then(m => ({ default: m.DocumentsPage })));
const CommunicationPage = lazy(() => import('./pages/communication/CommunicationPage').then(m => ({ default: m.CommunicationPage })));
const SecurityPage = lazy(() => import('./pages/security/SecurityPage').then(m => ({ default: m.SecurityPage })));
const ModulePage = lazy(() => import('./pages/ModulePage').then(m => ({ default: m.ModulePage })));
const SearchPage = lazy(() => import('./pages/search/SearchPage').then(m => ({ default: m.SearchPage })));
const SettingsPage = lazy(() => import('./pages/settings/SettingsPage').then(m => ({ default: m.SettingsPage })));

const BotList = lazy(() => import('./pages/webchat/BotList').then(m => ({ default: m.BotList })));
const BotEditor = lazy(() => import('./pages/webchat/BotEditor').then(m => ({ default: m.BotEditor })));
const ConversationsViewer = lazy(() => import('./pages/webchat/ConversationsViewer').then(m => ({ default: m.ConversationsViewer })));
const EmbedSnippetGenerator = lazy(() => import('./pages/webchat/EmbedSnippetGenerator').then(m => ({ default: m.EmbedSnippetGenerator })));
const TestSandbox = lazy(() => import('./pages/webchat/TestSandbox').then(m => ({ default: m.TestSandbox })));

const MarketingLayout = lazy(() => import('./pages/marketing/MarketingLayout').then(m => ({ default: m.MarketingLayout })));
const MarketingDashboard = lazy(() => import('./pages/marketing/Dashboard').then(m => ({ default: m.MarketingDashboard })));
const MarketingSettingsPage = lazy(() => import('./pages/marketing/Settings').then(m => ({ default: m.MarketingSettingsPage })));
const MarketingNavigationPage = lazy(() => import('./pages/marketing/Navigation').then(m => ({ default: m.MarketingNavigationPage })));
const MarketingPagesPage = lazy(() => import('./pages/marketing/Pages').then(m => ({ default: m.MarketingPagesPage })));
const MarketingTemplatesPage = lazy(() => import('./pages/marketing/Templates').then(m => ({ default: m.MarketingTemplatesPage })));
const MarketingPortfolioPage = lazy(() => import('./pages/marketing/Portfolio').then(m => ({ default: m.MarketingPortfolioPage })));
const MarketingPortfolioEditor = lazy(() => import('./pages/marketing/PortfolioEditor').then(m => ({ default: m.MarketingPortfolioEditor })));
const MarketingBlogPage = lazy(() => import('./pages/marketing/Blog').then(m => ({ default: m.MarketingBlogPage })));
const MarketingBlogEditor = lazy(() => import('./pages/marketing/BlogEditor').then(m => ({ default: m.MarketingBlogEditor })));
const MarketingServicesPage = lazy(() => import('./pages/marketing/Services').then(m => ({ default: m.MarketingServicesPage })));
const MarketingTestimonialsPage = lazy(() => import('./pages/marketing/Testimonials').then(m => ({ default: m.MarketingTestimonialsPage })));
const MarketingFAQsPage = lazy(() => import('./pages/marketing/FAQs').then(m => ({ default: m.MarketingFAQsPage })));
const MarketingTeamPage = lazy(() => import('./pages/marketing/Team').then(m => ({ default: m.MarketingTeamPage })));
const MarketingSocialPage = lazy(() => import('./pages/marketing/Social').then(m => ({ default: m.MarketingSocialPage })));
const MarketingMediaPage = lazy(() => import('./pages/marketing/Media').then(m => ({ default: m.MarketingMediaPage })));

const AcademicLayout = lazy(() => import('./pages/academic/AcademicLayout').then(m => ({ default: m.AcademicLayout })));
const AcademicDashboard = lazy(() => import('./pages/academic/Dashboard').then(m => ({ default: m.AcademicDashboard })));
const AcademicClassesPage = lazy(() => import('./pages/academic/Classes').then(m => ({ default: m.AcademicClassesPage })));
const AcademicClassDetailPage = lazy(() => import('./pages/academic/ClassDetail').then(m => ({ default: m.AcademicClassDetailPage })));
const AcademicAttendancePage = lazy(() => import('./pages/academic/Attendance').then(m => ({ default: m.AcademicAttendancePage })));
const AcademicTimetablePage = lazy(() => import('./pages/academic/Timetable').then(m => ({ default: m.AcademicTimetablePage })));
const AcademicLmsPage = lazy(() => import('./pages/academic/LmsLibrary').then(m => ({ default: m.AcademicLmsPage })));
const AcademicLabReportsPage = lazy(() => import('./pages/academic/LabReports').then(m => ({ default: m.AcademicLabReportsPage })));
const AcademicExamsPage = lazy(() => import('./pages/academic/Exams').then(m => ({ default: m.AcademicExamsPage })));
const AcademicAdvisingPage = lazy(() => import('./pages/academic/Advising').then(m => ({ default: m.AcademicAdvisingPage })));
const AcademicGroupProjectsPage = lazy(() => import('./pages/academic/GroupProjects').then(m => ({ default: m.AcademicGroupProjectsPage })));
const AcademicStudyAidsPage = lazy(() => import('./pages/academic/StudyAids').then(m => ({ default: m.AcademicStudyAidsPage })));
const AcademicStudyBuddiesPage = lazy(() => import('./pages/academic/StudyBuddies').then(m => ({ default: m.AcademicStudyBuddiesPage })));
const AcademicFinancePage = lazy(() => import('./pages/academic/Finance').then(m => ({ default: m.AcademicFinancePage })));
const AcademicDeadlinesPage = lazy(() => import('./pages/academic/Deadlines').then(m => ({ default: m.AcademicDeadlinesPage })));

const ConstructionLayout = lazy(() => import('./pages/construction/ConstructionLayout').then(m => ({ default: m.ConstructionLayout })));
const ConstructionProjectsList = lazy(() => import('./pages/construction/ProjectsList').then(m => ({ default: m.ConstructionProjectsList })));
const ConstructionDashboardPage = lazy(() => import('./pages/construction/ProjectDashboard').then(m => ({ default: m.ConstructionDashboardPage })));
const ConstructionRisksPage = lazy(() => import('./pages/construction/Risks').then(m => ({ default: m.ConstructionRisksPage })));
const ConstructionSchedulePage = lazy(() => import('./pages/construction/Schedule').then(m => ({ default: m.ConstructionSchedulePage })));
const ConstructionMilestonesPage = lazy(() => import('./pages/construction/Milestones').then(m => ({ default: m.ConstructionMilestonesPage })));
const ConstructionProgressPage = lazy(() => import('./pages/construction/Progress').then(m => ({ default: m.ConstructionProgressPage })));
const ConstructionPermitsPage = lazy(() => import('./pages/construction/Permits').then(m => ({ default: m.ConstructionPermitsPage })));
const ConstructionSiteInstructionsPage = lazy(() => import('./pages/construction/SiteInstructions').then(m => ({ default: m.ConstructionSiteInstructionsPage })));
const ConstructionVariationsPage = lazy(() => import('./pages/construction/Variations').then(m => ({ default: m.ConstructionVariationsPage })));
const ConstructionExtensionsPage = lazy(() => import('./pages/construction/Extensions').then(m => ({ default: m.ConstructionExtensionsPage })));
const ConstructionContractsPage = lazy(() => import('./pages/construction/Contracts').then(m => ({ default: m.ConstructionContractsPage })));
const ConstructionRaciPage = lazy(() => import('./pages/construction/Raci').then(m => ({ default: m.ConstructionRaciPage })));
const ConstructionInsurancesPage = lazy(() => import('./pages/construction/Insurances').then(m => ({ default: m.ConstructionInsurancesPage })));
const ConstructionToolboxPage = lazy(() => import('./pages/construction/Toolbox').then(m => ({ default: m.ConstructionToolboxPage })));
const NotFoundPage = lazy(() => import('./pages/NotFoundPage').then(m => ({ default: m.NotFoundPage })));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
});

function LazyFallback() {
  return (
    <div className="grid min-h-[40vh] place-items-center text-sm text-ink-muted">
      <p>Loading module…</p>
    </div>
  );
}

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

  // Read the user's reduced-motion preference so we can pass it down to
  // framer-motion globally. The OS-level prefers-reduced-motion is honoured
  // by framer-motion natively when MotionConfig is given "user"; combining
  // with our in-app override means infinite spins/shakes/pulses inside motion
  // components stop when either signal says "reduced".
  const reducedMotion = useThemeStore((s) => s.reducedMotion);
  return (
    <ErrorBoundary>
      <MotionConfig reducedMotion={reducedMotion ? 'always' : 'user'}>
      <QueryClientProvider client={queryClient}>
        {/* Router is selected at import time (see top of file):
            - Hosted web/SaaS:        BrowserRouter (clean URLs, SEO-friendly)
            - Packaged Electron:      HashRouter   (works under file://)
            - VITE_FORCE_ROUTER       can pin either at build time           */}
        <Router>
          <Suspense fallback={<LazyFallback />}>
            <Routes>
              <Route path="/login" element={<PublicOnly><LoginPage /></PublicOnly>} />
              <Route path="/register" element={<PublicOnly><RegisterPage /></PublicOnly>} />
              <Route path="/signup" element={<PublicOnly><SignupPage /></PublicOnly>} />
              <Route path="/auth/magic-link/sent" element={<PublicOnly><MagicLinkPage /></PublicOnly>} />
              <Route path="/auth/consume" element={<PublicOnly><ConsumeLinkPage /></PublicOnly>} />
              <Route path="/auth/accept-invite" element={<PublicOnly><AcceptInvitePage /></PublicOnly>} />
              <Route path="/" element={<Protected><AppShell /></Protected>}>
                <Route index element={<ErrorBoundary><DashboardPage /></ErrorBoundary>} />
                <Route path="settings" element={<ErrorBoundary><SettingsPage /></ErrorBoundary>} />
                <Route path="search" element={<ErrorBoundary><SearchPage /></ErrorBoundary>} />
                <Route path="finance" element={<ErrorBoundary><FinancePage /></ErrorBoundary>} />
                <Route path="hr" element={<ErrorBoundary><HRPage /></ErrorBoundary>} />
                <Route path="crm" element={<ErrorBoundary><CRMPage /></ErrorBoundary>} />
                <Route path="projects" element={<ErrorBoundary><ProjectsPage /></ErrorBoundary>} />
                <Route path="inventory" element={<ErrorBoundary><InventoryPage /></ErrorBoundary>} />
                <Route path="coding" element={<ErrorBoundary><CodingPage /></ErrorBoundary>} />
                <Route path="ai" element={<ErrorBoundary><AIBrainPage /></ErrorBoundary>} />
                <Route path="documents" element={<ErrorBoundary><DocumentsPage /></ErrorBoundary>} />
                <Route path="communication" element={<ErrorBoundary><CommunicationPage /></ErrorBoundary>} />
                <Route path="security" element={<ErrorBoundary><SecurityPage /></ErrorBoundary>} />
                <Route path="webchat" element={<ErrorBoundary><BotList /></ErrorBoundary>} />
                <Route path="webchat/bots/new" element={<ErrorBoundary><BotEditor /></ErrorBoundary>} />
                <Route path="webchat/bots/:botId/edit" element={<ErrorBoundary><BotEditor /></ErrorBoundary>} />
                <Route path="webchat/bots/:botId/conversations" element={<ErrorBoundary><ConversationsViewer /></ErrorBoundary>} />
                <Route path="webchat/bots/:botId/embed" element={<ErrorBoundary><EmbedSnippetGenerator /></ErrorBoundary>} />
                <Route path="webchat/bots/:botId/sandbox" element={<ErrorBoundary><TestSandbox /></ErrorBoundary>} />
                <Route path="marketing" element={<ErrorBoundary><MarketingLayout /></ErrorBoundary>}>
                  <Route index element={<MarketingDashboard />} />
                  <Route path="settings" element={<MarketingSettingsPage />} />
                  <Route path="navigation" element={<MarketingNavigationPage />} />
                  <Route path="pages" element={<MarketingPagesPage />} />
                  <Route path="templates" element={<MarketingTemplatesPage />} />
                  <Route path="portfolio" element={<MarketingPortfolioPage />} />
                  <Route path="portfolio/new" element={<MarketingPortfolioEditor />} />
                  <Route path="portfolio/:projectId" element={<MarketingPortfolioEditor />} />
                  <Route path="blog" element={<MarketingBlogPage />} />
                  <Route path="blog/new" element={<MarketingBlogEditor />} />
                  <Route path="blog/:postId" element={<MarketingBlogEditor />} />
                  <Route path="services" element={<MarketingServicesPage />} />
                  <Route path="testimonials" element={<MarketingTestimonialsPage />} />
                  <Route path="faqs" element={<MarketingFAQsPage />} />
                  <Route path="team" element={<MarketingTeamPage />} />
                  <Route path="social" element={<MarketingSocialPage />} />
                  <Route path="media" element={<MarketingMediaPage />} />
                </Route>
                <Route path="academic" element={<ErrorBoundary><AcademicLayout /></ErrorBoundary>}>
                  <Route index element={<AcademicDashboard />} />
                  <Route path="classes" element={<AcademicClassesPage />} />
                  <Route path="classes/:classId" element={<AcademicClassDetailPage />} />
                  <Route path="attendance" element={<AcademicAttendancePage />} />
                  <Route path="timetable" element={<AcademicTimetablePage />} />
                  <Route path="lms" element={<AcademicLmsPage />} />
                  <Route path="lab-reports" element={<AcademicLabReportsPage />} />
                  <Route path="exams" element={<AcademicExamsPage />} />
                  <Route path="advising" element={<AcademicAdvisingPage />} />
                  <Route path="group-projects" element={<AcademicGroupProjectsPage />} />
                  <Route path="study-aids" element={<AcademicStudyAidsPage />} />
                  <Route path="study-buddies" element={<AcademicStudyBuddiesPage />} />
                  <Route path="finance" element={<AcademicFinancePage />} />
                  <Route path="deadlines" element={<AcademicDeadlinesPage />} />
                </Route>
                <Route path="construction" element={<ErrorBoundary><ConstructionProjectsList /></ErrorBoundary>} />
                <Route path="construction/projects/:projectId" element={<ErrorBoundary><ConstructionLayout /></ErrorBoundary>}>
                  <Route index element={<ConstructionDashboardPage />} />
                  <Route path="risks" element={<ConstructionRisksPage />} />
                  <Route path="schedule" element={<ConstructionSchedulePage />} />
                  <Route path="milestones" element={<ConstructionMilestonesPage />} />
                  <Route path="progress" element={<ConstructionProgressPage />} />
                  <Route path="permits" element={<ConstructionPermitsPage />} />
                  <Route path="site-instructions" element={<ConstructionSiteInstructionsPage />} />
                  <Route path="variations" element={<ConstructionVariationsPage />} />
                  <Route path="extensions" element={<ConstructionExtensionsPage />} />
                  <Route path="contracts" element={<ConstructionContractsPage />} />
                  <Route path="raci" element={<ConstructionRaciPage />} />
                  <Route path="insurances" element={<ConstructionInsurancesPage />} />
                  <Route path="toolbox" element={<ConstructionToolboxPage />} />
                </Route>
                <Route path="org" element={<ErrorBoundary><OrgLayout /></ErrorBoundary>}>
                  <Route index element={<OrgGeneralTab />} />
                  <Route path="users" element={<OrgUsersTab />} />
                  <Route path="billing" element={<OrgBillingTab />} />
                  <Route path="sso" element={<OrgSSOTab />} />
                  <Route path="scim" element={<OrgSCIMTab />} />
                  <Route path="roles" element={<OrgRolesTab />} />
                  <Route path="encryption" element={<OrgEncryptionTab />} />
                  <Route path="security" element={<OrgSecurityTab />} />
                  <Route path="webhooks" element={<OrgWebhooksTab />} />
                  <Route path="privacy" element={<OrgPrivacyTab />} />
                  <Route path="usage" element={<OrgUsageTab />} />
                </Route>
                <Route path=":module" element={<ErrorBoundary><ModulePage /></ErrorBoundary>} />
                {/* Lost-in-space 404 — appears when no other route matched. */}
                <Route path="*" element={<NotFoundPage />} />
              </Route>
            </Routes>
          </Suspense>
        </Router>
        <Toaster
          position="top-right"
          gutter={10}
          toastOptions={{
            duration: 4200,
            className: 'text-sm',
            style: {
              background: 'rgb(var(--color-surface-elevated) / 0.92)',
              color: 'rgb(var(--color-ink))',
              border: '1px solid rgb(var(--color-border))',
              boxShadow: '0 10px 30px -5px rgb(0 0 0 / 0.18), 0 4px 12px -2px rgb(0 0 0 / 0.08)',
              backdropFilter: 'blur(12px)',
              WebkitBackdropFilter: 'blur(12px)',
              borderRadius: '12px',
              padding: '10px 14px',
            },
            success: {
              iconTheme: { primary: 'rgb(16 185 129)', secondary: 'white' },
              style: { borderLeft: '3px solid rgb(16 185 129)' },
            },
            error: {
              iconTheme: { primary: 'rgb(244 63 94)', secondary: 'white' },
              style: { borderLeft: '3px solid rgb(244 63 94)' },
            },
          }}
        />
      </QueryClientProvider>
      </MotionConfig>
    </ErrorBoundary>
  );
}
