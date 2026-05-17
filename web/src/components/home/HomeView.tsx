import { useNavigate } from 'react-router-dom';
import { useApi } from '../../hooks/useApi';
import { api } from '../../api/client';
import type { ProjectSummary } from '../../types';

export function HomeView() {
  const { data, loading } = useApi(() => api.projects(), []);
  const navigate = useNavigate();

  const projects: ProjectSummary[] = data?.projects ?? [];

  return (
    <div className="h-full flex items-center justify-center bg-surface">
      <div className="w-full max-w-lg px-8">
        <div className="text-center mb-10">
          <h1 className="text-cyber text-3xl font-mono font-bold mb-2">rommer</h1>
          <p className="text-text-muted text-sm">AI-driven reverse engineering platform</p>
        </div>

        {/* Existing projects */}
        {!loading && projects.length > 0 && (
          <div className="mb-6">
            <div className="text-[10px] uppercase tracking-widest text-text-muted mb-3 font-bold">
              // projects
            </div>
            <div className="space-y-2">
              {projects.map((p) => (
                <button
                  key={p.name}
                  onClick={() => navigate(`/project/${p.name}`)}
                  className="w-full text-left px-4 py-3 border border-border-dim rounded bg-surface-raised hover:border-cyber transition-colors"
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-sm font-mono text-text-primary">
                        {p.game_title || p.name}
                      </div>
                      <div className="text-[10px] text-text-muted mt-0.5">
                        {p.name} &middot; {p.platform || 'unknown'}
                      </div>
                    </div>
                    <span className="text-cyber text-xs font-mono">&gt;</span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {loading && (
          <div className="text-text-muted text-sm font-mono text-center mb-6">Loading projects...</div>
        )}

        {/* New project */}
        <button
          onClick={() => navigate('/new')}
          className="w-full py-3 bg-cyber/10 border border-cyber text-cyber font-mono text-sm rounded hover:bg-cyber/20 transition-colors"
        >
          + New Project
        </button>
      </div>
    </div>
  );
}
