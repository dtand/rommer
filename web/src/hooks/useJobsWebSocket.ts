import { useEffect, useRef, useCallback, useState } from 'react';
import { toast } from '../components/layout/Toast';

interface JobEvent {
  type: 'job_started' | 'job_progress' | 'job_complete' | 'job_failed' | 'job_cancelled' | 'pong';
  job_id?: string;
  project?: string;
  data?: { step?: string; percent?: number; message?: string; summary?: string };
  error?: string;
}

interface JobUpdate {
  job_id: string;
  status?: string;
  progress?: { step: string; percent: number; message: string } | null;
  error?: string;
}

export function useJobsWebSocket(project: string | undefined) {
  const wsRef = useRef<WebSocket | null>(null);
  const [updates, setUpdates] = useState<Map<string, JobUpdate>>(new Map());
  const reconnectRef = useRef<ReturnType<typeof setTimeout>>();

  const connect = useCallback(() => {
    if (!project) return;

    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${proto}//${window.location.host}/api/ws?project=${project}`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      // Send periodic pings to keep alive
      const ping = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send('ping');
      }, 30000);
      ws.addEventListener('close', () => clearInterval(ping));
    };

    ws.onmessage = (event) => {
      try {
        const data: JobEvent = JSON.parse(event.data);
        if (data.type === 'pong') return;

        const jobId = data.job_id;
        if (!jobId) return;

        setUpdates(prev => {
          const next = new Map(prev);
          const existing = next.get(jobId) || { job_id: jobId };

          if (data.type === 'job_progress') {
            existing.progress = data.data as JobUpdate['progress'];
            existing.status = 'running';
          } else if (data.type === 'job_complete') {
            existing.status = 'completed';
            existing.progress = null;
            toast('success', data.data?.summary || 'Job completed');
          } else if (data.type === 'job_failed') {
            existing.status = 'failed';
            existing.error = data.error;
            toast('error', `Job failed: ${data.error}`);
          } else if (data.type === 'job_cancelled') {
            existing.status = 'cancelled';
          } else if (data.type === 'job_started') {
            existing.status = 'running';
          }

          next.set(jobId, existing);
          return next;
        });
      } catch { /* ignore parse errors */ }
    };

    ws.onclose = () => {
      // Reconnect after 3s
      reconnectRef.current = setTimeout(connect, 3000);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [project]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return updates;
}
