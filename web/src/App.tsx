import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppShell } from './components/layout/AppShell';
import { ProjectView } from './components/project/ProjectView';
import { GraphView } from './components/graph/GraphView';
import { DataView } from './components/data/DataView';
import { WalkthroughView } from './components/walkthrough/WalkthroughView';
import { UploadView } from './components/upload/UploadView';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/new" element={<UploadView />} />
        <Route element={<AppShell />}>
          <Route path="/project/:name" element={<ProjectView />} />
          <Route path="/project/:name/graph" element={<GraphView />} />
          <Route path="/project/:name/data" element={<DataView />} />
          <Route path="/project/:name/walkthrough" element={<WalkthroughView />} />
          <Route path="/" element={<Navigate to="/new" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
