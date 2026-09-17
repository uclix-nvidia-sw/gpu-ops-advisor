import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Component, StrictMode, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { Shell } from './components/Shell';
import { Empty } from './components/ui';
import { AppProvider } from './lib/store';
import { Cases } from './pages/Cases';
import { Dashboard } from './pages/Dashboard';
import { Fleet } from './pages/Fleet';
import { JobDetail, Jobs } from './pages/Jobs';
import { Knowledge } from './pages/Knowledge';
import { ReportForm, Reports } from './pages/Reports';
import { ResultPage } from './pages/Results';
import { Schedules } from './pages/Schedules';
import { Settings } from './pages/Settings';
import { Backend } from './pages/Backend';
import './styles.css';
class ErrorBoundary extends Component<{ children: ReactNode }, { error: boolean }> {
  state = { error: false };
  static getDerivedStateFromError() {
    return { error: true };
  }
  render() {
    return this.state.error ? (
      <div className="error-boundary">
        <h1>화면을 불러오지 못했습니다.</h1>
        <p>새로고침 후 다시 확인해 주세요. 서버에 저장된 기록은 유지됩니다.</p>
        <button className="button primary" onClick={() => location.reload()}>
          다시 불러오기
        </button>
      </div>
    ) : (
      this.props.children
    );
  }
}
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: true } },
});
const root = import.meta.hot?.data.root ?? createRoot(document.getElementById('root')!);
if (import.meta.hot) import.meta.hot.data.root = root;
root.render(
  <StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <AppProvider>
          <BrowserRouter>
            <Routes>
              <Route element={<Shell />}>
                <Route index element={<Navigate to="/dashboard" replace />} />
                <Route path="dashboard" element={<Dashboard />} />
                <Route path="fleet" element={<Navigate to="/fleet/assets" replace />} />
                <Route path="fleet/assets" element={<Fleet key="assets" view="assets" />} />
                <Route
                  path="fleet/workloads"
                  element={<Fleet key="workloads" view="workloads" />}
                />
                <Route path="fleet/quality" element={<Fleet key="quality" view="quality" />} />
                <Route path="cases" element={<Cases />} />
                <Route path="analyses/new" element={<Navigate to="/cases" replace />} />
                <Route path="analyses/:id" element={<ResultPage kind="analysis" />} />
                <Route path="incidents/:id" element={<ResultPage kind="incident" />} />
                <Route path="reports" element={<Reports />} />
                <Route path="reports/new" element={<ReportForm />} />
                <Route path="reports/:id" element={<ResultPage kind="report" />} />
                <Route path="schedules" element={<Schedules />} />
                <Route path="schedules/:id" element={<Schedules />} />
                <Route path="jobs" element={<Jobs />} />
                <Route path="jobs/:id" element={<JobDetail />} />
                <Route path="knowledge" element={<Knowledge />} />
                <Route path="settings" element={<Navigate to="/settings/models" replace />} />
                <Route path="settings/models" element={<Settings key="models" view="models" />} />
                <Route path="settings/backend" element={<Backend />} />
                <Route
                  path="settings/routing"
                  element={<Settings key="routing" view="routing" />}
                />
                <Route path="settings/data" element={<Settings key="data" view="data" />} />
                <Route
                  path="*"
                  element={
                    <Empty
                      title="페이지를 찾을 수 없습니다."
                      action={
                        <a className="button primary" href="/dashboard">
                          대시보드로 이동
                        </a>
                      }
                    />
                  }
                />
              </Route>
            </Routes>
          </BrowserRouter>
        </AppProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  </StrictMode>,
);
