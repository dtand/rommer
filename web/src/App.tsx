import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AppShell } from './components/layout/AppShell';
import { ToastContainer } from './components/layout/Toast';
import { HomeView } from './components/home/HomeView';
import { ProjectView } from './components/project/ProjectView';
import { GraphView } from './components/graph/GraphView';
import { DataView } from './components/data/DataView';
import { WalkthroughView } from './components/walkthrough/WalkthroughView';
import { JobsView } from './components/jobs/JobsView';
import { AnalysisView } from './components/analysis/AnalysisView';
import { UploadView } from './components/upload/UploadView';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomeView />} />
        <Route path="/new" element={<UploadView />} />
        <Route element={<AppShell />}>
          <Route path="/project/:name" element={<ProjectView />} />
          <Route path="/project/:name/graph" element={<GraphView />} />
          <Route path="/project/:name/data" element={<DataView />} />
          <Route path="/project/:name/walkthrough" element={<WalkthroughView />} />
          <Route path="/project/:name/jobs" element={<JobsView />} />
          <Route path="/project/:name/analysis" element={<AnalysisView />} />
        </Route>
      </Routes>
      <ToastContainer />
    </BrowserRouter>
  );
}
