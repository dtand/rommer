import { Outlet, useNavigate } from 'react-router-dom';
import { useApi } from '../../hooks/useApi';
import { api } from '../../api/client';
import type { ProjectSummary } from '../../types';

export function AppShell() {
  const { data } = useApi(() => api.projects(), []);
  const navigate = useNavigate();

  const projects = data?.projects ?? [];

  return (
    <div className="flex h-full bg-surface">
      <nav className="w-56 bg-black text-text-secondary flex flex-col h-full shrink-0 border-r border-border-dim">
        <div className="p-4 border-b border-border-dim">
          <div className="text-[10px] uppercase tracking-widest text-cyber-muted mb-2 font-bold">// rommer</div>
          <select
            className="w-full bg-surface-raised border border-border text-cyber text-sm px-2 py-1.5 rounded font-mono cursor-pointer focus:outline-none focus:border-cyber"
            onChange={(e) => {
              const val = e.target.value;
              if (val === '__new__') navigate('/new');
              else if (val) navigate(`/project/${val}`);
            }}
            defaultValue=""
          >
            <option value="" disabled>Select project...</option>
            {projects.map((p: ProjectSummary) => (
              <option key={p.name} value={p.name}>
                {p.game_title || p.name}
              </option>
            ))}
            <option value="__new__">+ New Project</option>
          </select>
        </div>
        <div className="flex-1" />
        <div className="p-4 border-t border-border-dim">
          <div className="text-[10px] text-text-muted font-mono">ROMMER v0.1</div>
        </div>
      </nav>
      <main className="flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  );
}
