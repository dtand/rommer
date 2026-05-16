import { useState, useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { useApi } from '../../hooks/useApi';
import { useJobsWebSocket } from '../../hooks/useJobsWebSocket';
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

interface JobEvent {
  id: number;
  type: string;
  timestamp: string;
  data: { step?: string; percent?: number; message?: string; summary?: string; error?: string } | null;
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
  const wsUpdates = useJobsWebSocket(name);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);

  if (loading) {
    return <div className="p-8 text-text-muted font-mono text-sm">Loading jobs...</div>;
  }

  const baseJobs: Job[] = (data?.jobs as Job[]) ?? [];
  const jobs = baseJobs.map(job => {
    const update = wsUpdates.get(job.id);
    if (!update) return job;
    return {
      ...job,
      status: update.status || job.status,
      progress: update.progress !== undefined ? update.progress : job.progress,
      error: update.error || job.error,
    };
  });

  const selectedJob = jobs.find(j => j.id === selectedJobId) || null;

  return (
    <div className="flex h-full">
      {/* Job list */}
      <div className="w-96 border-r border-border-dim overflow-y-auto h-full shrink-0">
        <div className="p-4 border-b border-border-dim sticky top-0 bg-surface-raised z-10">
          <div className="flex items-center justify-between">
            <div className="text-[10px] uppercase tracking-widest text-cyber-muted font-bold">
              // jobs ({jobs.length})
            </div>
            <div className="flex gap-1">
              <KickButton label="Graph" onClick={() => api.startJob(name!, 'graph-gen')} />
              <KickButton label="Know." onClick={() => api.startJob(name!, 'knowledge-analysis')} />
              <KickButton label="Ghidra" onClick={() => api.startJob(name!, 'ghidra-decompile')} />
            </div>
          </div>
        </div>

        {jobs.length === 0 ? (
          <div className="p-4 text-text-muted text-sm font-mono text-center mt-4">
            No jobs yet.
          </div>
        ) : (
          <div className="divide-y divide-border-dim">
            {jobs.map((job) => (
              <JobRow
                key={job.id}
                job={job}
                selected={selectedJobId === job.id}
                onClick={() => setSelectedJobId(job.id)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Job detail / log panel */}
      <div className="flex-1 overflow-hidden h-full">
        {selectedJob ? (
          <JobDetail job={selectedJob} />
        ) : (
          <div className="flex items-center justify-center h-full text-text-muted font-mono text-sm">
            Select a job to view logs
          </div>
        )}
      </div>
    </div>
  );
}

function JobRow({ job, selected, onClick }: { job: Job; selected: boolean; onClick: () => void }) {
  const isRunning = job.status === 'running';
  const lastMessage = job.progress?.message || job.progress?.step || '';

  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-4 py-3 transition-colors ${
        selected ? 'bg-cyber-bg border-r-2 border-cyber' : 'hover:bg-surface-overlay'
      }`}
    >
      <div className="flex items-center justify-between">
        <span className="text-sm font-mono text-text-primary">
          {TYPE_LABELS[job.type] || job.type}
        </span>
        <span className={`text-[10px] font-mono flex items-center gap-1 ${STATUS_COLORS[job.status]}`}>
          {job.status}
          {isRunning && <span className="inline-block w-1.5 h-1.5 bg-yellow-400 rounded-full animate-pulse" />}
        </span>
      </div>
      {/* Last message */}
      {(isRunning || job.status === 'completed') && lastMessage && (
        <div className="text-[10px] text-text-muted mt-1 truncate">{lastMessage}</div>
      )}
      {job.error && (
        <div className="text-[10px] text-red-400 mt-1 truncate">{job.error}</div>
      )}
      {/* Progress bar inline */}
      {job.progress && isRunning && (
        <div className="h-1 bg-surface-overlay rounded-full overflow-hidden mt-1.5">
          <div className="h-full bg-cyber transition-all duration-500" style={{ width: `${job.progress.percent}%` }} />
        </div>
      )}
    </button>
  );
}

function JobDetail({ job }: { job: Job }) {
  const { data } = useApi(() => api.jobEvents(job.id), [job.id]);
  const logEndRef = useRef<HTMLDivElement>(null);
  const events: JobEvent[] = (data?.events as JobEvent[]) ?? [];

  // Auto-scroll to bottom when new events arrive
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events.length]);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b border-border-dim bg-surface-raised shrink-0">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-mono text-text-primary">{TYPE_LABELS[job.type] || job.type}</div>
            <div className="text-[10px] text-text-muted font-mono mt-0.5">{job.id}</div>
          </div>
          <div className="flex items-center gap-3">
            <span className={`text-xs font-mono ${STATUS_COLORS[job.status]}`}>{job.status}</span>
            {job.status === 'running' && (
              <button
                onClick={() => api.cancelJob(job.id)}
                className="text-[10px] px-2 py-1 border border-red-800 text-red-400 rounded hover:bg-red-900/20 font-mono"
              >
                Cancel
              </button>
            )}
          </div>
        </div>
        {/* Progress bar */}
        {job.progress && (
          <div className="mt-3">
            <div className="flex items-center justify-between text-[10px] text-text-muted mb-1">
              <span>{job.progress.step}</span>
              <span>{job.progress.percent}%</span>
            </div>
            <div className="h-1.5 bg-surface-overlay rounded-full overflow-hidden">
              <div className="h-full bg-cyber transition-all duration-500" style={{ width: `${job.progress.percent}%` }} />
            </div>
            {job.progress.message && (
              <div className="text-[10px] text-text-muted mt-1">{job.progress.message}</div>
            )}
          </div>
        )}
      </div>

      {/* Event log */}
      <div className="flex-1 overflow-y-auto p-4 font-mono text-xs">
        {events.length === 0 ? (
          <div className="text-text-muted">No events yet...</div>
        ) : (
          <div className="space-y-1.5">
            {events.map((evt) => (
              <EventLine key={evt.id} event={evt} />
            ))}
            <div ref={logEndRef} />
          </div>
        )}
      </div>
    </div>
  );
}

function EventLine({ event }: { event: JobEvent }) {
  const time = new Date(event.timestamp).toLocaleTimeString();
  const typeColors: Record<string, string> = {
    progress: 'text-cyber-dim',
    result: 'text-cyber',
    error: 'text-red-400',
    log: 'text-text-secondary',
  };

  let message = '';
  if (event.data) {
    if (event.type === 'progress') {
      message = `[${event.data.percent}%] ${event.data.step}${event.data.message ? ' — ' + event.data.message : ''}`;
    } else if (event.type === 'result') {
      message = event.data.summary || 'Completed';
    } else if (event.type === 'error') {
      message = event.data.error || 'Unknown error';
    } else {
      message = JSON.stringify(event.data);
    }
  }

  return (
    <div className="flex gap-2">
      <span className="text-text-muted shrink-0">{time}</span>
      <span className={`${typeColors[event.type] || 'text-text-secondary'}`}>{message}</span>
    </div>
  );
}

function KickButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="text-[10px] px-1.5 py-0.5 border border-border text-text-secondary rounded hover:border-cyber hover:text-cyber font-mono transition-colors"
    >
      {label}
    </button>
  );
}
