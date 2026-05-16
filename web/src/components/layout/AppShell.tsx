import { Outlet, useNavigate, useParams, NavLink, useLocation } from 'react-router-dom';
import { useApi } from '../../hooks/useApi';
import { api } from '../../api/client';
import type { ProjectSummary } from '../../types';

const navItems = [
  { path: '', label: 'Dashboard', icon: '~' },
  { path: '/graph', label: 'Graph', icon: '>' },
  { path: '/data', label: 'Data', icon: '#' },
  { path: '/walkthrough', label: 'Walkthrough', icon: '"' },
  { path: '/jobs', label: 'Jobs', icon: '!' },
];

export function AppShell() {
  const { data } = useApi(() => api.projects(), []);
  const navigate = useNavigate();
  const location = useLocation();

  const projects = data?.projects ?? [];

  // Extract current project name from URL
  const match = location.pathname.match(/^\/project\/([^/]+)/);
  const currentProject = match ? match[1] : '';

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
            value={currentProject}
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

        {currentProject && (
          <div className="flex-1 py-2">
            {navItems.map((item) => (
              <NavLink
                key={item.path}
                to={`/project/${currentProject}${item.path}`}
                end
                className={({ isActive }) =>
                  `flex items-center gap-2 px-4 py-2.5 text-sm font-mono transition-colors ${
                    isActive
                      ? 'bg-cyber-bg text-cyber border-r-2 border-cyber'
                      : 'hover:bg-cyber-bg/50 hover:text-cyber-dim text-text-muted'
                  }`
                }
              >
                <span className="text-xs text-cyber-muted">{item.icon}</span>
                {item.label}
              </NavLink>
            ))}
          </div>
        )}

        {!currentProject && <div className="flex-1" />}

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
