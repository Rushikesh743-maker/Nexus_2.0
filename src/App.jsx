import { BrowserRouter, HashRouter } from 'react-router-dom';

/**
 * Sandboxed preview frames run on an opaque origin where history.pushState
 * is blocked. Probe once and fall back to hash routing — route structure is
 * identical either way.
 */
function detectRouter() {
  try {
    window.history.pushState(null, '', window.location.href);
    return BrowserRouter;
  } catch {
    return HashRouter;
  }
}
import { ThemeProvider } from '@/context/ThemeContext';
import { AuthProvider } from '@/context/AuthContext';
import { ToastProvider } from '@/context/ToastContext';
import { ProtectedRoute, PublicOnlyRoute } from '@/router/guards';
import { AppLayout } from '@/components/layout/AppLayout';
import { LoginPage } from '@/pages/LoginPage';
import { DashboardPage } from '@/pages/DashboardPage';
import { InvestigationsPage } from '@/pages/investigations/InvestigationsPage';
import { NewInvestigationPage } from '@/pages/investigations/NewInvestigationPage';
import { InvestigationLayout } from '@/pages/investigations/InvestigationLayout';
import { OverviewPage } from '@/pages/investigations/OverviewPage';
import { WorkspacePage } from '@/pages/investigations/WorkspacePage';
import { EvidencePage } from '@/pages/investigations/EvidencePage';
import { NetworkPage } from '@/pages/investigations/NetworkPage';
import { MapPage } from '@/pages/investigations/MapPage';
import { TimelinePage } from '@/pages/investigations/TimelinePage';
import { IntelligencePage } from '@/pages/investigations/IntelligencePage';
import { ReportsPage } from '@/pages/investigations/ReportsPage';
import { AnalysisLayout } from '@/pages/analysis/AnalysisLayout';
import { AnalysisOverviewPage } from '@/pages/analysis/AnalysisOverviewPage';
import { AnalysisGraphPage } from '@/pages/analysis/AnalysisGraphPage';
import { AnalysisMapPage } from '@/pages/analysis/AnalysisMapPage';
import { KeyPeoplePage } from '@/pages/analysis/KeyPeoplePage';
import { PatternsPage } from '@/pages/analysis/PatternsPage';
import { LinkAnalysisPage } from '@/pages/analysis/LinkAnalysisPage';
import { PipelinePage } from '@/pages/analysis/PipelinePage';
import { ConflictsPage } from '@/pages/analysis/ConflictsPage';
import { AskPage } from '@/pages/analysis/AskPage';
import { SystemPage } from '@/pages/analysis/SystemPage';
import { SettingsPage } from '@/pages/settings/SettingsPage';
import { NotFoundPage } from '@/pages/NotFoundPage';
import { Navigate, Route, Routes } from 'react-router-dom';

export default function App() {
  const Router = detectRouter();
  return (
    <Router
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <ThemeProvider>
        <AuthProvider>
          <ToastProvider>
            <Routes>
              {/* Public */}
              <Route
                path="/login"
                element={
                  <PublicOnlyRoute>
                    <LoginPage />
                  </PublicOnlyRoute>
                }
              />

              {/* Protected shell */}
              <Route
                element={
                  <ProtectedRoute>
                    <AppLayout />
                  </ProtectedRoute>
                }
              >
                <Route path="/" element={<Navigate to="/dashboard" replace />} />
                <Route path="/dashboard" element={<DashboardPage />} />
                <Route path="/investigations" element={<InvestigationsPage />} />
                <Route path="/investigations/new" element={<NewInvestigationPage />} />
                <Route path="/investigations/:id" element={<InvestigationLayout />}>
                  <Route index element={<OverviewPage />} />
                  <Route path="workspace" element={<WorkspacePage />} />
                  <Route path="evidence" element={<EvidencePage />} />
                  <Route path="network" element={<NetworkPage />} />
                  <Route path="map" element={<MapPage />} />
                  <Route path="timeline" element={<TimelinePage />} />
                  <Route path="intelligence" element={<IntelligencePage />} />
                  <Route path="reports" element={<ReportsPage />} />

                  {/* Criminal-network-analysis surfaces, served by backend/. */}
                  <Route path="analysis" element={<AnalysisLayout />}>
                    <Route index element={<AnalysisOverviewPage />} />
                    <Route path="graph" element={<AnalysisGraphPage />} />
                  <Route path="map" element={<AnalysisMapPage />} />
                    <Route path="people" element={<KeyPeoplePage />} />
                    <Route path="patterns" element={<PatternsPage />} />
                    <Route path="conflicts" element={<ConflictsPage />} />
                    <Route path="links" element={<LinkAnalysisPage />} />
                    <Route path="pipeline" element={<PipelinePage />} />
                    <Route path="ask" element={<AskPage />} />
                    <Route path="system" element={<SystemPage />} />
                  </Route>
                </Route>
                <Route path="/settings" element={<SettingsPage />} />
              </Route>

              {/* Fallback */}
              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </ToastProvider>
        </AuthProvider>
      </ThemeProvider>
    </Router>
  );
}
