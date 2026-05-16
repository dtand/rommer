import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppShell } from './components/layout/AppShell';
import { ProjectView } from './components/project/ProjectView';
import { UploadView } from './components/upload/UploadView';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/new" element={<UploadView />} />
        <Route element={<AppShell />}>
          <Route path="/project/:name" element={<ProjectView />} />
          <Route path="/" element={<Navigate to="/new" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
