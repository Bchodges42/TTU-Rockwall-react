export function eqClass(s) {
  s = (s || '').toLowerCase()
  if (s.includes('available')) return 'c-ok'
  if (s.includes('limited')) return 'c-warn'
  return 'c-err'
}
export function eventStatus(ev) {
  const left = ev.spots_total - ev.spots_filled
  if (left > 0) return { cls: 'c-info', txt: `${left} spots left` }
  return { cls: 'c-warn', txt: `Full · ${ev.next_date}` }
}
