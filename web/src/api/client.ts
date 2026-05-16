const BASE = '/api';

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

async function patchJson<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

async function postFormData<T>(path: string, formData: FormData): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

import type { ProjectSummary, ProjectDetail, InitProjectResult } from '../types';

export const api = {
  projects: () => fetchJson<{ projects: ProjectSummary[] }>('/projects'),
  project: (name: string) => fetchJson<ProjectDetail>(`/project?name=${name}`),

  initProject: (name: string, platform: string, file: File): Promise<InitProjectResult> => {
    const formData = new FormData();
    formData.append('name', name);
    formData.append('platform', platform);
    formData.append('file', file);
    return postFormData<InitProjectResult>('/init-project', formData);
  },

  startPipeline: (project: string, walkthrough: string | null, model: string = 'opus') =>
    postJson<Record<string, unknown>>(`/project/${project}/start-pipeline`, { walkthrough, model }),

  graphNodes: (project: string) =>
    fetchJson<{ nodes: Record<string, unknown>[] }>(`/graph/nodes?project=${project}`),

  discoveries: (project: string, tier?: string) => {
    const params = tier ? `&tier=${tier}` : '';
    return fetchJson<{ discoveries: Record<string, unknown>[] }>(`/graph/discoveries?project=${project}${params}`);
  },

  updateDiscoveryTier: (project: string, discoveryId: number, tier: string) =>
    patchJson<{ ok: boolean }>(`/graph/discoveries/${discoveryId}/tier?project=${project}`, { tier }),

  sections: (project: string) =>
    fetchJson<{ sections: Record<string, unknown>[] }>(`/graph/sections?project=${project}`),

  // Jobs
  jobs: (project: string) =>
    fetchJson<{ jobs: Record<string, unknown>[] }>(`/jobs?project=${project}`),

  startJob: (project: string, type: string, config?: Record<string, unknown>) =>
    postJson<{ job_id: string }>(`/jobs/${type}`, { project, ...config }),

  cancelJob: (jobId: string) =>
    postJson<{ ok: boolean }>(`/jobs/${jobId}/cancel`),

  jobEvents: (jobId: string) =>
    fetchJson<{ events: Record<string, unknown>[] }>(`/jobs/${jobId}/events`),
};
