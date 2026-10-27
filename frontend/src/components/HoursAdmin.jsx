import { useEffect, useState } from 'react'
import { adminService } from '../services/rockwallService.js'
import { fmtDay, fmtTime, halfHours } from '../services/format.js'

const TIMES = halfHours('06:00', '23:30')

// Weekly hours drive the whole site: the open/closed line, the booking window (closed days
// disappear), and booking validation. Normally they sync from TTU's hours page on their own.
export default function HoursAdmin({ onChanged }) {
  const [state, setState] = useState(null)
  const [week, setWeek] = useState([])
  const [closure, setClosure] = useState({ day: '', reason: '' })
  const [msg, setMsg] = useState(null)
  const [busy, setBusy] = useState(false)

  function apply(next, text) {
    setState(next); setWeek(next.weekly)
    if (text) setMsg({ type: 'ok', text })
    onChanged()
  }
  useEffect(() => { adminService.hours().then(next => { setState(next); setWeek(next.weekly) }).catch(e => setMsg({ type: 'err', text: e.message })) }, [])

  async function run(action, text) {
    setBusy(true)
    try { const next = await action(); apply(next, next.message || text) }
    catch (e) { setMsg({ type: 'err', text: e.message }) }
    finally { setBusy(false) }
  }
  const setDay = (weekday, patch) => setWeek(w => w.map(d => d.weekday === weekday ? { ...d, ...patch } : d))

  if (!state) return null
  return (
    <section className="tile mt">
      <div className="tile-head"><h2>Hours</h2>
        <label className="toggle"><input type="checkbox" checked={state.auto_sync} disabled={busy}
          onChange={e => run(() => adminService.saveHours({ auto_sync: e.target.checked }), e.target.checked ? 'Auto-sync on.' : 'Auto-sync off.')} /> Sync from tntech.edu</label>
      </div>
      <div className="tile-body stack">
        {msg && <p className={`note ${msg.type} plain`}>{msg.text}</p>}
        <p className="muted small plain">
          {state.sync_status}{state.synced_at ? ` (${new Date(state.synced_at).toLocaleString()})` : ''} ·{' '}
          <a href={state.source} target="_blank" rel="noreferrer">TTU hours page ↗</a>
        </p>
        <div className="hours-grid">
          {week.map(d => (
            <div className="hours-row" key={d.weekday}>
              <span className="fw600">{d.name}</span>
              <label className="toggle"><input type="checkbox" checked={!d.opens}
                onChange={e => setDay(d.weekday, e.target.checked ? { opens: null, closes: null } : { opens: '14:00', closes: '19:00' })} /> Closed</label>
              {d.opens ? <>
                <select className="select" aria-label={`${d.name} opens`} value={d.opens} onChange={e => setDay(d.weekday, { opens: e.target.value })}>{TIMES.map(t => <option key={t} value={t}>{fmtTime(t)}</option>)}</select>
                <select className="select" aria-label={`${d.name} closes`} value={d.closes} onChange={e => setDay(d.weekday, { closes: e.target.value })}>{TIMES.map(t => <option key={t} value={t}>{fmtTime(t)}</option>)}</select>
              </> : <span className="muted small span2">Not shown in the booking window</span>}
            </div>
          ))}
        </div>
        <div className="row">
          <button className="btn btn-primary" disabled={busy} onClick={() => run(() => adminService.saveHours({ weekly: week.map(({ weekday, opens, closes }) => ({ weekday, opens, closes })) }), 'Hours saved. Auto-sync is off so your edit sticks.')}>Save hours</button>
          <button className="btn" disabled={busy} onClick={() => run(() => adminService.syncHours())}>Sync from TTU now</button>
        </div>

        <h3 className="sub-h">One-off closures</h3>
        {state.closures.length === 0 && <p className="muted small plain">None coming up.</p>}
        {state.closures.map(c => (
          <div className="list-row" key={c.day}>
            <span className="grow"><b>{fmtDay(c.day, 'short')}</b> · {c.reason}</span>
            <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => run(() => adminService.removeClosure(c.day), 'Closure removed.')}>Remove</button>
          </div>
        ))}
        <form className="row add-form" onSubmit={e => { e.preventDefault(); if (closure.day) run(() => adminService.addClosure(closure.day, closure.reason)).then(() => setClosure({ day: '', reason: '' })) }}>
          <div className="field plain"><label htmlFor="cl-day">Date</label><input id="cl-day" className="input" type="date" value={closure.day} onChange={e => setClosure(c => ({ ...c, day: e.target.value }))} /></div>
          <div className="field grow plain"><label htmlFor="cl-reason">Reason</label><input id="cl-reason" className="input" placeholder="Holiday, route reset…" value={closure.reason} onChange={e => setClosure(c => ({ ...c, reason: e.target.value }))} /></div>
          <button className="btn" disabled={busy || !closure.day}>Close that day</button>
        </form>
      </div>
    </section>
  )
}
