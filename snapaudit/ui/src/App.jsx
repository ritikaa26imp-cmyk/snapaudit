import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout.jsx';
import AuditLogPage from './pages/AuditLogPage.jsx';
import BulkPage from './pages/BulkPage.jsx';
import ComparisonPage from './pages/ComparisonPage.jsx';
import PolicyPage from './pages/PolicyPage.jsx';
import VisibilityPage from './pages/VisibilityPage.jsx';

/**
 * Top-level routes; every screen shares `Layout` (nav + outlet).
 */
export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<ComparisonPage />} />
          <Route path="bulk" element={<BulkPage />} />
          <Route path="audits" element={<AuditLogPage />} />
          <Route path="visibility" element={<VisibilityPage />} />
          <Route path="policy" element={<PolicyPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
