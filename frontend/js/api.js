// Thin wrapper around the backend REST API.

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch { /* ignore */ }
    const error = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) return null;
  return response.json();
}

export const api = {
  schema: () => request('/api/schema'),

  listProjects: () => request('/api/projects'),
  getProject: (id) => request(`/api/projects/${encodeURIComponent(id)}`),
  createProject: (project) => request('/api/projects', {
    method: 'POST', body: JSON.stringify(project),
  }),
  updateProject: (id, project) => request(`/api/projects/${encodeURIComponent(id)}`, {
    method: 'PUT', body: JSON.stringify(project),
  }),
  deleteProject: (id) => request(`/api/projects/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  generate: (project) => request('/api/generate/template', {
    method: 'POST', body: JSON.stringify(project),
  }),

  validate: (project) => request('/api/validate', {
    method: 'POST', body: JSON.stringify(project),
  }),

  preview: (project, accent = 'red') => request('/api/preview', {
    method: 'POST', body: JSON.stringify({ project, accent }),
  }),

  getSettings: () => request('/api/settings'),
  saveSettings: (settings) => request('/api/settings', {
    method: 'POST', body: JSON.stringify(settings),
  }),

  haStatus: () => request('/api/ha/status'),
  haEntities: (domain) => request(`/api/ha/entities${domain ? `?domain=${encodeURIComponent(domain)}` : ''}`),
  haPush: (payload) => request('/api/ha/push', {
    method: 'POST', body: JSON.stringify(payload),
  }),
};
