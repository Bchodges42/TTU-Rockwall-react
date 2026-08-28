const API = '/api'
const ADMIN_HEADERS = { 'X-Admin': 'admin@tntech.edu' }

async function request(path, { method = 'GET', body, admin = false } = {}) {
  const response = await fetch(`${API}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', ...(admin ? ADMIN_HEADERS : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`)
  return data
}

export async function loadRockwallData(includeAdmin = false) {
  const [capacity, events, faqs, equipment, peak, leaderboard, routes, feedback, siteContent, appointments] = await Promise.all([
    request('/capacity'), request('/events'), request('/faqs'), request('/equipment'), request('/peak'),
    request('/leaderboard'), request('/routes'), request('/feedback'), request('/site-content'),
    includeAdmin ? request('/appointments', { admin: true }) : Promise.resolve([]),
  ])
  return { capacity, events, faqs, equipment, peak, leaderboard, routes, feedback, siteContent, appointments }
}

export const authService = {
  login: (email, password) => request('/login', { method: 'POST', body: { email, password } }),
  register: (form) => request('/register', { method: 'POST', body: form }),
}

export const bookingService = {
  availability: (date) => request(`/availability?date=${encodeURIComponent(date)}`),
  create: (appointment) => request('/appointments', { method: 'POST', body: appointment }),
  verify: (id, admin = false) => request(`/appointments/${encodeURIComponent(id)}`, { admin }),
  update: (id, patch) => request(`/appointments/${id}`, { method: 'PATCH', body: patch, admin: true }),
  remove: (id) => request(`/appointments/${id}`, { method: 'DELETE', admin: true }),
}

export const adminService = {
  setCapacity: (max) => request('/admin/capacity', { method: 'PUT', body: { max }, admin: true }),
  setSiteContent: (key, value) => request('/admin/site-content', { method: 'PUT', body: { k: key, v: value }, admin: true }),
  addFaq: (question, answer) => request('/admin/faqs', { method: 'POST', body: { q: question, a: answer }, admin: true }),
  removeFaq: (id) => request(`/admin/faqs/${id}`, { method: 'DELETE', admin: true }),
  addEvent: (event) => request('/admin/events', { method: 'POST', body: event, admin: true }),
  renameEvent: (id, name) => request(`/admin/events/${id}`, { method: 'PATCH', body: { name }, admin: true }),
  removeEvent: (id) => request(`/admin/events/${id}`, { method: 'DELETE', admin: true }),
}

export const feedbackService = {
  create: (feedback) => request('/feedback', { method: 'POST', body: feedback }),
}
