import { useParams } from 'react-router-dom';
import { useApi } from '../../hooks/useApi';
import { api } from '../../api/client';

export function ProjectView() {
  const { name } = useParams<{ name: string }>();
  const { data: project, loading, error } = useApi(() => api.project(name!), [name]);

  if (loading) {
    return (
      <div className="p-8">
        <div className="text-text-muted font-mono text-sm">Loading project...</div>
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="p-8">
        <div className="text-red-400 font-mono text-sm">Error: {error || 'Project not found'}</div>
      </div>
    );
  }

  return (
    <div className="p-8 max-w-4xl">
      {/* Header */}
      <div className="mb-8">
        <div className="text-[10px] uppercase tracking-widest text-cyber-muted mb-1 font-bold">
          // {project.platform}
        </div>
        <h1 className="text-cyber text-xl font-mono font-bold">
          {project.game_title || project.name}
        </h1>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        <StatCard label="Graph Nodes" value={project.stats.graph_nodes} />
        <StatCard label="Discoveries" value={project.stats.discoveries} />
        <StatCard label="Golden" value={project.stats.golden} />
        <StatCard label="Edges" value={project.stats.graph_edges} />
      </div>

      {/* Next steps */}
      <div className="border border-border-dim rounded p-4 bg-surface-raised">
        <div className="text-[10px] uppercase tracking-widest text-text-muted mb-3 font-bold">
          // next steps
        </div>
        {project.stats.graph_nodes === 0 ? (
          <div className="space-y-2">
            <div className="flex items-center gap-3">
              <span className="text-cyber">1.</span>
              <span className="text-text-primary text-sm">
                Run <code className="text-cyber bg-cyber-bg px-1.5 py-0.5 rounded">rommer build-graph --project {name}</code> to generate the walkthrough graph
              </span>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-text-muted">2.</span>
              <span className="text-text-muted text-sm">Launch analysis agents</span>
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            <div className="flex items-center gap-3">
              <span className="text-cyber">&#10003;</span>
              <span className="text-text-primary text-sm">
                Graph generated ({project.stats.graph_nodes} nodes)
              </span>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-cyber">1.</span>
              <span className="text-text-primary text-sm">
                Run <code className="text-cyber bg-cyber-bg px-1.5 py-0.5 rounded">rommer launch-agent --project {name} --agent dynamic</code>
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="border border-border-dim rounded p-3 bg-surface-raised">
      <div className="text-[10px] uppercase tracking-widest text-text-muted mb-1">{label}</div>
      <div className="text-cyber text-xl font-mono font-bold">{value}</div>
    </div>
  );
}
