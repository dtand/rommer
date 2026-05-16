import { useParams } from 'react-router-dom';
import { useApi } from '../../hooks/useApi';
import { api } from '../../api/client';
import type { KnowledgeFile } from '../../types';

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

  // Group knowledge files by category
  const byCategory: Record<string, KnowledgeFile[]> = {};
  for (const f of project.knowledge || []) {
    byCategory[f.category] = byCategory[f.category] || [];
    byCategory[f.category].push(f);
  }

  return (
    <div className="p-8 h-full overflow-y-auto">
      {/* Header */}
      <div className="mb-8">
        <div className="text-[10px] uppercase tracking-widest text-cyber-muted mb-1 font-bold">
          // {project.platform}
        </div>
        <h1 className="text-cyber text-xl font-mono font-bold">
          {project.game_title || project.name}
        </h1>
      </div>

      {/* ROM Metadata */}
      {project.rom && (
        <div className="border border-border-dim rounded p-4 bg-surface-raised mb-6">
          <div className="text-[10px] uppercase tracking-widest text-text-muted mb-3 font-bold">
            // rom info
          </div>
          <div className="grid grid-cols-3 gap-x-8 gap-y-2 text-sm font-mono">
            <Field label="Title" value={project.rom.game_title} />
            <Field label="Game Code" value={project.rom.game_code} />
            <Field label="Developer" value={project.rom.maker_name} />
            <Field label="Region" value={project.rom.region} />
            <Field label="Size" value={`${project.rom.rom_size_mb} MB`} />
            <Field label="Checksum" value={project.rom.checksum_valid ? 'Valid' : 'INVALID'} highlight={!project.rom.checksum_valid} />
          </div>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <StatCard label="Graph Nodes" value={project.stats.graph_nodes} />
        <StatCard label="Discoveries" value={project.stats.discoveries} />
        <StatCard label="Golden" value={project.stats.golden} />
        <StatCard label="Edges" value={project.stats.graph_edges} />
      </div>

      {/* Knowledge Resources */}
      {Object.keys(byCategory).length > 0 && (
        <div className="border border-border-dim rounded p-4 bg-surface-raised mb-6">
          <div className="text-[10px] uppercase tracking-widest text-text-muted mb-3 font-bold">
            // knowledge resources
          </div>
          <div className="space-y-4">
            {Object.entries(byCategory).map(([category, files]) => (
              <div key={category}>
                <div className="text-cyber-dim text-xs font-mono mb-1.5 uppercase">{category}</div>
                <div className="space-y-1">
                  {files.map((f) => (
                    <div key={f.path} className="flex items-center justify-between text-sm font-mono py-0.5">
                      <span className="text-text-primary truncate">{f.name}</span>
                      <span className="text-text-muted text-xs ml-4 shrink-0">{formatSize(f.size)}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Next steps */}
      <div className="border border-border-dim rounded p-4 bg-surface-raised">
        <div className="text-[10px] uppercase tracking-widest text-text-muted mb-3 font-bold">
          // next steps
        </div>
        {project.stats.graph_nodes === 0 ? (
          <div className="space-y-2">
            <Step num="1" active>
              Run <Code>rommer build-graph --project {name}</Code> to generate the walkthrough graph
            </Step>
            <Step num="2">Launch analysis agents</Step>
            <Step num="3">Review and promote discoveries</Step>
          </div>
        ) : (
          <div className="space-y-2">
            <Step num="✓" active={false}>
              Graph generated ({project.stats.graph_nodes} nodes)
            </Step>
            <Step num="1" active>
              Run <Code>rommer launch-agent --project {name} --agent dynamic</Code>
            </Step>
            <Step num="2">Review candidates and promote to golden</Step>
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

function Field({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div>
      <span className="text-text-muted">{label}: </span>
      <span className={highlight ? 'text-red-400' : 'text-text-primary'}>{value}</span>
    </div>
  );
}

function Step({ num, active, children }: { num: string; active?: boolean; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3">
      <span className={active ? 'text-cyber' : 'text-text-muted'}>{num}.</span>
      <span className={`text-sm ${active ? 'text-text-primary' : 'text-text-muted'}`}>{children}</span>
    </div>
  );
}

function Code({ children }: { children: React.ReactNode }) {
  return <code className="text-cyber bg-cyber-bg px-1.5 py-0.5 rounded">{children}</code>;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)}KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}
