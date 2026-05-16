import { useParams } from 'react-router-dom';
import { useApi } from '../../hooks/useApi';
import { api } from '../../api/client';

interface Job {
  id: string;
  type: string;
  status: string;
  progress: { step: string; percent: number; message: string } | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
}

const TYPE_LABELS: Record<string, string> = {
  graph_gen: 'Graph Generation',
  knowledge_analysis: 'Knowledge Analysis',
  ghidra_decompile: 'Ghidra Decompile',
  agent: 'Analysis Agent',
};

const STATUS_COLORS: Record<string, string> = {
  pending: 'text-text-muted',
  running: 'text-yellow-400',
  completed: 'text-cyber',
  failed: 'text-red-400',
  cancelled: 'text-text-muted',
};

export function JobsView() {
  const { name } = useParams<{ name: string }>();
  const { data, loading } = useApi(() => api.jobs(name!), [name]);

  if (loading) {
    return <div className="p-8 text-text-muted font-mono text-sm">Loading jobs...</div>;
  }

  const jobs: Job[] = data?.jobs ?? [];

  return (
    <div className="p-6 h-full overflow-y-auto">
      <div className="flex items-center justify-between mb-4">
        <div className="text-[10px] uppercase tracking-widest text-cyber-muted font-bold">
          // jobs ({jobs.length})
        </div>
        <div className="flex gap-2">
          <KickButton label="Graph Gen" onClick={() => api.startJob(name!, 'graph-gen')} />
          <KickButton label="Knowledge" onClick={() => api.startJob(name!, 'knowledge-analysis')} />
          <KickButton label="Ghidra" onClick={() => api.startJob(name!, 'ghidra-decompile')} />
        </div>
      </div>

      {jobs.length === 0 ? (
        <div className="text-text-muted text-sm font-mono mt-8 text-center">
          No jobs yet. Jobs are created automatically after project setup,<br />
          or you can kick them off manually above.
        </div>
      ) : (
        <div className="space-y-3">
          {jobs.map((job) => (
            <JobCard key={job.id} job={job} project={name!} />
          ))}
        </div>
      )}
    </div>
  );
}

function JobCard({ job, project }: { job: Job; project: string }) {
  const isRunning = job.status === 'running';

  return (
    <div className="border border-border-dim rounded p-4 bg-surface-raised">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-3">
          <span className="text-sm font-mono text-text-primary">
            {TYPE_LABELS[job.type] || job.type}
          </span>
          <span className={`text-xs font-mono ${STATUS_COLORS[job.status] || 'text-text-muted'}`}>
            {job.status}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {isRunning && (
            <button
              onClick={() => api.cancelJob(job.id)}
              className="text-[10px] px-2 py-1 border border-red-800 text-red-400 rounded hover:bg-red-900/20 font-mono"
            >
              Cancel
            </button>
          )}
          <span className="text-[10px] text-text-muted font-mono">{job.id}</span>
        </div>
      </div>

      {/* Progress bar */}
      {job.progress && (
        <div className="mt-2">
          <div className="flex items-center justify-between text-[10px] text-text-muted mb-1">
            <span>{job.progress.step}</span>
            <span>{job.progress.percent}%</span>
          </div>
          <div className="h-1.5 bg-surface-overlay rounded-full overflow-hidden">
            <div
              className="h-full bg-cyber transition-all duration-300"
              style={{ width: `${job.progress.percent}%` }}
            />
          </div>
          {job.progress.message && (
            <div className="text-[10px] text-text-muted mt-1">{job.progress.message}</div>
          )}
        </div>
      )}

      {/* Error */}
      {job.error && (
        <div className="mt-2 text-xs text-red-400 font-mono bg-red-900/10 p-2 rounded">
          {job.error}
        </div>
      )}

      {/* Timestamps */}
      <div className="mt-2 text-[10px] text-text-muted font-mono">
        {job.completed_at && `Completed: ${new Date(job.completed_at).toLocaleString()}`}
        {!job.completed_at && job.started_at && `Started: ${new Date(job.started_at).toLocaleString()}`}
        {!job.started_at && `Created: ${new Date(job.created_at).toLocaleString()}`}
      </div>
    </div>
  );
}

function KickButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="text-[10px] px-2 py-1 border border-border text-text-secondary rounded hover:border-cyber hover:text-cyber font-mono transition-colors"
    >
      {label}
    </button>
  );
}
