const API = '/api'

async function request(path, { method = 'GET', body } = {}) {
  const response = await fetch(`${API}${path}`, {
    method,
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map(item => item.msg).join('; ') : data.detail
    throw new Error(detail || `Request failed (${response.status})`)
  }
  return data
}

export async function loadRockwallData(includeAdmin = false) {
  const [capacity, events, faqs, equipment, peak, leaderboard, routes, feedback, siteContent, appointments] = await Promise.all([
    request('/capacity'), request('/events'), request('/faqs'), request('/equipment'), request('/peak'),
    request('/leaderboard'), request('/routes'), request('/feedback'), request('/site-content'),
    includeAdmin ? request('/appointments') : Promise.resolve([]),
  ])
  return { capacity, events, faqs, equipment, peak, leaderboard, routes, feedback, siteContent, appointments }
}

export const authService = {
  me: () => request('/me'),
  logout: () => request('/logout', { method: 'POST' }),
  login: (email, password) => request('/login', { method: 'POST', body: { email, password } }),
  register: (form) => request('/register', { method: 'POST', body: form }),
}

export const bookingService = {
  availability: (date) => request(`/availability?date=${encodeURIComponent(date)}`),
  create: (appointment) => request('/appointments', { method: 'POST', body: appointment }),
  verify: (id) => request(`/appointments/${encodeURIComponent(id)}`),
  update: (id, patch) => request(`/appointments/${id}`, { method: 'PATCH', body: patch }),
  remove: (id) => request(`/appointments/${id}`, { method: 'DELETE' }),
}

export const adminService = {
  setCapacity: (max) => request('/admin/capacity', { method: 'PUT', body: { max } }),
  setSiteContent: (key, value) => request('/admin/site-content', { method: 'PUT', body: { k: key, v: value } }),
  addFaq: (question, answer) => request('/admin/faqs', { method: 'POST', body: { q: question, a: answer } }),
  removeFaq: (id) => request(`/admin/faqs/${id}`, { method: 'DELETE' }),
  addEvent: (event) => request('/admin/events', { method: 'POST', body: event }),
  renameEvent: (id, name) => request(`/admin/events/${id}`, { method: 'PATCH', body: { name } }),
  removeEvent: (id) => request(`/admin/events/${id}`, { method: 'DELETE' }),
}

export const feedbackService = {
  create: (feedback) => request('/feedback', { method: 'POST', body: feedback }),
}

export const queueService = {
  list: () => request('/queue'),
  add: (entry) => request('/queue', { method: 'POST', body: entry }),
  change: (id, action) => request(`/queue/${id}`, { method: 'PATCH', body: { action } }),
}
