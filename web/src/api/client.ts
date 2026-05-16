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

  knowledgeFiles: (project: string) =>
    fetchJson<{ files: { path: string; type: string; size: number }[] }>(`/project/${project}/knowledge`),
};
