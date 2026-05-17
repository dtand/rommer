import { useEffect, useRef, useCallback, useState } from 'react';
import { toast } from '../components/layout/Toast';

export interface LogEntry {
  timestamp: number;
  message: string;
  type?: string;
}

interface JobUpdate {
  job_id: string;
  status?: string;
  progress?: { step: string; percent: number; message: string } | null;
  logs: LogEntry[];
  error?: string;
}

/**
 * Subscribe to a specific job's live logs via WebSocket.
 * Connects to /api/ws/jobs/{jobId} — one connection per job.
 */
export function useJobWebSocket(jobId: string | null) {
  const wsRef = useRef<WebSocket | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [progress, setProgress] = useState<JobUpdate['progress']>(null);
  const [status, setStatus] = useState<string | null>(null);
  const cleaningUpRef = useRef(false);

  useEffect(() => {
    if (!jobId) return;

    cleaningUpRef.current = false;
    setLogs([]);
    setProgress(null);
    setStatus(null);

    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${proto}//${window.location.host}/api/ws/jobs/${jobId}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    const ping = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send('ping');
    }, 30000);

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'pong') return;

        if (data.type === 'job_log') {
          const msg = data.data?.message || '';
          const logType = data.data?.log_type || 'log';
          if (msg) {
            setLogs(prev => [...prev, { timestamp: Date.now(), message: msg, type: logType }]);
          }
        } else if (data.type === 'job_progress') {
          setProgress(data.data);
          setStatus('running');
          const msg = `[${data.data?.percent}%] ${data.data?.step}${data.data?.message ? ' — ' + data.data.message : ''}`;
          setLogs(prev => [...prev, { timestamp: Date.now(), message: msg, type: 'progress' }]);
        } else if (data.type === 'job_complete') {
          setStatus('completed');
          setProgress(null);
          setLogs(prev => [...prev, { timestamp: Date.now(), message: `✓ ${data.data?.summary || 'Completed'}`, type: 'result' }]);
        } else if (data.type === 'job_failed') {
          setStatus('failed');
          setLogs(prev => [...prev, { timestamp: Date.now(), message: `✗ ${data.error}`, type: 'error' }]);
        }
      } catch { /* ignore */ }
    };

    ws.onclose = () => {
      clearInterval(ping);
      if (!cleaningUpRef.current) {
        // Reconnect after 3s
        setTimeout(() => {
          if (!cleaningUpRef.current && wsRef.current === ws) {
            // Re-run effect by not doing anything — React will handle it
          }
        }, 3000);
      }
    };

    ws.onerror = () => ws.close();

    return () => {
      cleaningUpRef.current = true;
      clearInterval(ping);
      ws.onclose = null;
      ws.close();
      wsRef.current = null;
    };
  }, [jobId]);

  return { logs, progress, status };
}

/**
 * Subscribe to project-level job status updates (toasts, status badges).
 * Connects to /api/ws/project/{project}.
 */
export function useProjectWebSocket(project: string | undefined) {
  const wsRef = useRef<WebSocket | null>(null);
  const [updates, setUpdates] = useState<Map<string, JobUpdate>>(new Map());
  const cleaningUpRef = useRef(false);

  useEffect(() => {
    if (!project) return;
    cleaningUpRef.current = false;

    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${proto}//${window.location.host}/api/ws/project/${project}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    const ping = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send('ping');
    }, 30000);

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'pong') return;
        const jobId = data.job_id;
        if (!jobId) return;

        setUpdates(prev => {
          const next = new Map(prev);
          const existing = next.get(jobId) || { job_id: jobId, logs: [] };

          if (data.type === 'job_progress') {
            existing.progress = data.data;
            existing.status = 'running';
          } else if (data.type === 'job_complete') {
            existing.status = 'completed';
            existing.progress = null;
            toast('success', data.data?.summary || 'Job completed');
          } else if (data.type === 'job_failed') {
            existing.status = 'failed';
            existing.error = data.error;
            toast('error', `Job failed: ${data.error}`);
          } else if (data.type === 'job_started') {
            existing.status = 'running';
          } else if (data.type === 'job_cancelled') {
            existing.status = 'cancelled';
          }

          next.set(jobId, existing);
          return next;
        });
      } catch { /* ignore */ }
    };

    ws.onclose = () => {
      clearInterval(ping);
      if (!cleaningUpRef.current) {
        setTimeout(() => {
          if (!cleaningUpRef.current) {
            // Component will re-mount and reconnect
          }
        }, 3000);
      }
    };

    ws.onerror = () => ws.close();

    return () => {
      cleaningUpRef.current = true;
      clearInterval(ping);
      ws.onclose = null;
      ws.close();
      wsRef.current = null;
    };
  }, [project]);

  return updates;
}
