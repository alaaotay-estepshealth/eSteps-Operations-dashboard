import axios from 'axios'

const BASE = import.meta.env.VITE_API_URL || '/api'

const api = axios.create({ baseURL: BASE })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      // Clear creds, then redirect — but only once, and never when already on /login,
      // otherwise we get an infinite reload loop from background pollers (AlertBanner etc.).
      localStorage.removeItem('token')
      localStorage.removeItem('role')
      if (window.location.pathname !== '/login') {
        window.location.replace('/login')
      }
    }
    return Promise.reject(err)
  }
)

export const authAPI = {
  login: (username, password) => {
    const form = new FormData()
    form.append('username', username)
    form.append('password', password)
    return api.post('/auth/token', form)
  },
}

export const adminAPI = {
  getMetrics: () => api.get('/admin/dashboard/metrics'),
  getActivityFeed: () => api.get('/admin/dashboard/activity-feed'),
  getSystemHealth: () => api.get('/admin/dashboard/system-health'),
  getWorkflowStatus: () => api.get('/admin/workflows/status'),
  getDailyExecutions: (days = 14) => api.get(`/admin/workflows/executions/daily?days=${days}`),
  getAIDecisions: (params = {}) => api.get('/admin/ai/decisions', { params }),
  getLogs: (params = {}) => api.get('/admin/logs/operations', { params }),
  getPipelineLeads: (params = {}) => api.get('/admin/pipeline/leads', { params }),
  getResearchStats: () => api.get('/admin/pipeline/research-stats'),
  getAlerts: () => api.get('/admin/dashboard/alerts'),
  getInsights: () => api.get('/admin/insights'),
  getBriefing: () => api.get('/admin/briefing'),
  getHeatmap: () => api.get('/admin/insights/heatmap'),
  generateMemo: () => api.post('/admin/insights/memo'),
  askAssistant: (question) => api.post('/admin/insights/assistant', { question }),
  getFollowups: () => api.get('/admin/followups'),
  getContacts: (params = {}) => api.get('/admin/contacts', { params }),
  getContact: (leadId) => api.get(`/admin/contacts/${encodeURIComponent(leadId)}`),
  getPriorityQueue: (limit = 12) => api.get('/admin/contacts/priority', { params: { limit } }),
  leadAction: (leadId, body) => api.post(`/admin/leads/${encodeURIComponent(leadId)}/action`, body),
  getReviewQueue: () => api.get('/admin/human-review/queue'),
  resolveReview: (id, resolution) => api.post(`/admin/human-review/queue/${id}/resolve`, resolution),
  syncN8n: (limit = 100) => api.post(`/admin/sync-n8n?limit=${limit}`),
  resolveWorkflowFailure: (executionId) =>
    api.post(`/admin/workflows/executions/${encodeURIComponent(executionId)}/resolve`),
}

export const systemsAPI = {
  listSystems: () => api.get('/admin/systems'),
  getOverview: () => api.get('/admin/systems/overview'),
  getSystemStats: (slug, days = 7) => api.get(`/admin/systems/${slug}`, { params: { days } }),
  getSystemExecutions: (slug, params = {}) => api.get(`/admin/systems/${slug}/executions`, { params }),
  getSystemActivity: (slug) => api.get(`/admin/systems/${slug}/activity`),
}

export const n8nAPI = {
  listWorkflows: () => api.get('/proxy/n8n/workflows'),
  executeWorkflow: (id) => api.post(`/proxy/n8n/workflows/${id}/execute`),
  activateWorkflow: (id) => api.post(`/proxy/n8n/workflows/${id}/activate`),
  deactivateWorkflow: (id) => api.post(`/proxy/n8n/workflows/${id}/deactivate`),
}

export const openclawAPI = {
  status: () => api.get('/admin/openclaw/status'),
  runAgent: (body) => api.post('/admin/openclaw/agent', body),
  wake: (text) => api.post('/admin/openclaw/wake', { text }),
}

export const emailsAPI = {
  getStats: () => api.get('/admin/emails/stats'),
  getLogs: (params = {}) => api.get('/admin/emails/logs', { params }),
}

export const bookingsAPI = {
  getStats: () => api.get('/admin/bookings/stats'),
  list: (params = {}) => api.get('/admin/bookings', { params }),
}

export const opportunitiesAPI = {
  getStats: () => api.get('/admin/opportunities/stats'),
  list: (params = {}) => api.get('/admin/opportunities', { params }),
}

export const ticketsAPI = {
  getStats: () => api.get('/admin/tickets/stats'),
  list: (params = {}) => api.get('/admin/tickets', { params }),
  updateStatus: (id, data) => api.patch(`/admin/tickets/${id}/status`, data),
  aiTriage: (ticketId) => api.post(`/admin/tickets/${ticketId}/ai-triage`),
}

export const calendarAPI = {
  meetings: (from, to) => api.get('/admin/bookings/calendar', { params: { from, to } }),
}

export const usersAPI = {
  list:   () => api.get('/admin/users'),
  me:     () => api.get('/admin/users/me'),
  create: (payload) => api.post('/admin/users', payload),
  update: (id, payload) => api.patch(`/admin/users/${id}`, payload),
  remove: (id) => api.delete(`/admin/users/${id}`),
}

function assetExplorerAPI(base) {
  return {
    getTree: () => api.get(`${base}/tree`),
    getStrategy: (path) => api.get(`${base}/strategy/${encodeURI(path)}`),
    downloadUrl: (path) => `${api.defaults.baseURL}${base}/download/${encodeURI(path)}`,
    // Fetch the file with the auth header so we can render it inline via blob URL.
    fetchBlob: (path, mime = 'application/octet-stream') =>
      api.get(`${base}/download/${encodeURI(path)}`, { responseType: 'blob' })
        .then(res => new Blob([res.data], { type: mime })),
    upload: (formData, onProgress) => api.post(`${base}/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: onProgress,
    }),
    createFolder: (path) => {
      const fd = new FormData()
      fd.append('path', path)
      return api.post(`${base}/folder`, fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    },
    remove: (path) => api.delete(`${base}/${encodeURI(path)}`),
  }
}

export const gtmAPI = {
  listStrategies: () => api.get('/admin/gtm/strategies'),
  ...assetExplorerAPI('/admin/gtm'),
}

export const meetsAPI = {
  ...assetExplorerAPI('/admin/meets'),
}

export const meetingsAPI = {
  list:    (params = {}) => api.get('/admin/meetings', { params }),
  get:     (bookingId) => api.get(`/admin/meetings/${bookingId}`),
  patchNotes: (bookingId, body) => api.patch(`/admin/meetings/${bookingId}/notes`, body),
  createTask: (bookingId, body) => api.post(`/admin/meetings/${bookingId}/tasks`, body),
  updateTask: (bookingId, taskId, body) =>
    api.patch(`/admin/meetings/${bookingId}/tasks/${taskId}`, body),
  deleteTask: (bookingId, taskId) =>
    api.delete(`/admin/meetings/${bookingId}/tasks/${taskId}`),
  aiDraft: (bookingId, force = false) =>
    api.post(`/admin/meetings/${bookingId}/ai-draft`, { force }),
  sync: (body = { source: 'manual' }) => api.post('/admin/meetings/sync', body),
}

export const suggestionsAPI = {
  apply:    (id, overridePayload) =>
    api.post(`/admin/suggestions/${id}/apply`, { override_payload: overridePayload || null }),
  reject:   (id, reason) =>
    api.post(`/admin/suggestions/${id}/reject`, { reason: reason || null }),
  pending:  (params = {}) => api.get('/admin/suggestions/pending', { params }),
  forTicket: (ticketId) => api.get(`/admin/tickets/${ticketId}/suggestions`),
}

export const gtmPlanAPI = {
  getPlan: () => api.get('/admin/insights/gtm-plan'),
  getInitiatives: () => api.get('/admin/insights/gtm-plan/initiatives'),
  generate: (force = false) => api.post('/admin/insights/gtm-plan/generate', { force }),
  applyInitiative: (id) => api.post(`/admin/insights/gtm-plan/initiatives/${id}/apply`),
  rejectInitiative: (id) => api.post(`/admin/insights/gtm-plan/initiatives/${id}/reject`),
}

export const gtmTasksAPI = {
  list: (params = {}) => api.get('/admin/gtm-tasks', { params }),
  calendar: (from, to) => api.get('/admin/gtm-tasks/calendar', { params: { from, to } }),
  assign: (id, userId) => api.post(`/admin/gtm-tasks/${id}/assign`, { user_id: userId }),
}

export default api
