import { Navigate, Route, Routes } from 'react-router-dom';
import AppShell from './components/layout/AppShell';
import Landing from './pages/Landing';
import Dashboard from './pages/Dashboard';
import NewResearch from './pages/NewResearch';
import ReportPage from './pages/ReportPage';
import History from './pages/History';
import Compare from './pages/Compare';
import Trends from './pages/Trends';
import SavedTopics from './pages/SavedTopics';
import Settings from './pages/Settings';
import About from './pages/About';

export default function App() {
  return (
    <Routes>
      {/* Public landing page */}
      <Route path="/" element={<Landing />} />

      {/* Authenticated-style app shell (no auth in v1 — single-instance workspace) */}
      <Route element={<AppShell />}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/research" element={<NewResearch />} />
        <Route path="/history" element={<History />} />
        <Route path="/compare" element={<Compare />} />
        <Route path="/trends" element={<Trends />} />
        <Route path="/topics" element={<SavedTopics />} />
        <Route path="/report/:id" element={<ReportPage />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/about" element={<About />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
