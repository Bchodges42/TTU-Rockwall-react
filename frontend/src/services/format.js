// Display helpers for the wall's local times ("14:30" -> "2:30 PM").
export function fmtTime(hhmm) {
  if (!hhmm) return ''
  const [h, m] = hhmm.split(':').map(Number)
  return `${h % 12 || 12}${m ? `:${String(m).padStart(2, '0')}` : ''} ${h < 12 ? 'AM' : 'PM'}`
}

export function fmtWindow(start, end) {
  return `${fmtTime(start)} – ${fmtTime(end)}`
}

function localDate(iso) {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d)
}

export function fmtDay(iso, style = 'long') {
  return localDate(iso).toLocaleDateString(undefined, style === 'long'
    ? { weekday: 'long', month: 'long', day: 'numeric' }
    : { weekday: 'short', month: 'short', day: 'numeric' })
}

// "today", "tomorrow", or the weekday name, relative to the visitor's clock.
export function relDay(iso) {
  const today = new Date(); today.setHours(0, 0, 0, 0)
  const diff = Math.round((localDate(iso) - today) / 86400000)
  if (diff === 0) return 'today'
  if (diff === 1) return 'tomorrow'
  return localDate(iso).toLocaleDateString(undefined, { weekday: 'long' })
}

// Half-hour boundaries between two times, inclusive.
export function halfHours(from = '06:00', to = '23:30') {
  const out = []
  for (let [h, m] = from.split(':').map(Number); h * 60 + m <= Number(to.slice(0, 2)) * 60 + Number(to.slice(3)); m += 30) {
    if (m === 60) { h += 1; m = 0 }
    out.push(`${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`)
  }
  return out
}
