import { lazy, Suspense } from 'react';
import { Route, Routes } from 'react-router-dom';
import { RequireAuth } from '@/auth/RequireAuth';
import { AppLayout } from '@/components/layout/AppLayout';
import { LoadingState } from '@/components/ui';
import { DocumentsPage } from '@/pages/DocumentsPage';
import { LoginPage } from '@/pages/LoginPage';
import { NotFoundPage } from '@/pages/NotFoundPage';
import { OverviewPage } from '@/pages/OverviewPage';
import { RegisterPage } from '@/pages/RegisterPage';
import { ReviewQueuePage } from '@/pages/ReviewQueuePage';
import { SettingsPage } from '@/pages/SettingsPage';

// Heavier pages (charts, file viewer, editor) are split into their own chunks.
const AnalyticsPage = lazy(() =>
  import('@/pages/AnalyticsPage').then((m) => ({ default: m.AnalyticsPage })),
);
const DocumentDetailPage = lazy(() =>
  import('@/pages/DocumentDetailPage').then((m) => ({ default: m.DocumentDetailPage })),
);
const ReviewEditorPage = lazy(() =>
  import('@/pages/ReviewEditorPage').then((m) => ({ default: m.ReviewEditorPage })),
);
const UploadPage = lazy(() =>
  import('@/pages/UploadPage').then((m) => ({ default: m.UploadPage })),
);

export function App() {
  return (
    <Suspense fallback={<LoadingState />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route element={<RequireAuth />}>
          <Route element={<AppLayout />}>
            <Route index element={<OverviewPage />} />
            <Route path="upload" element={<UploadPage />} />
            <Route path="documents" element={<DocumentsPage />} />
            <Route path="documents/:documentId" element={<DocumentDetailPage />} />
            <Route path="review" element={<ReviewQueuePage />} />
            <Route path="review/:documentId" element={<ReviewEditorPage />} />
            <Route path="analytics" element={<AnalyticsPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Route>
      </Routes>
    </Suspense>
  );
}
