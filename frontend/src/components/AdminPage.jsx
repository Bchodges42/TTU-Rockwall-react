import { useState } from 'react'
import { Chip } from './Chip.jsx'
import HoursAdmin from './HoursAdmin.jsx'
import { adminService, bookingService } from '../services/rockwallService.js'
import { fmtWindow, halfHours } from '../services/format.js'

// Hours are no longer free text: they come from the hours pipeline (see HoursAdmin).
const CONTENT_FIELDS = ['site_title', 'site_kicker', 'hero_title']
const PLACEHOLDERS = {
  site_title: 'TTU Rockwall',
  site_kicker: 'Campus Recreation · Climbing Wall',
  hero_title: 'Where campus learns to climb.',
}
const TIMES = halfHours('06:00', '23:30')
const EMPTY_EVENT = { name: '', spots_total: 20, spots_filled: 0, next_date: '', link: '' }

// Admin portal — owns its own form state; server data comes in via `data`.
export default function AdminPage({ data, onDataChanged }) {
  const [draft, setDraft] = useState(data.siteContent)
  const [adminMax, setAdminMax] = useState('')
  const [adminOnline, setAdminOnline] = useState('')
  const [newFaq, setNewFaq] = useState({ q: '', a: '' })
  const [newEventName, setNewEventName] = useState('')
  const [editing, setEditing] = useState(null) // { id, name, date, time }
  const [msg, setMsg] = useState(null)

  async function run(action, okText) {
    try {
      const out = await action()
      setMsg({ type: 'ok', text: typeof okText === 'function' ? okText(out) : (out.message || okText) })
      onDataChanged()
      return true
    } catch (error) { setMsg({ type: 'err', text: error.message }) }
  }

  const saveContent = e => { e.preventDefault(); run(async () => { await Promise.all(CONTENT_FIELDS.map(k => adminService.setSiteContent(k, draft[k] || ''))); return { message: 'Site content updated.' } }) }
  const saveCapacity = e => { e.preventDefault(); run(() => adminService.setCapacity(Number(adminMax || data.capacity.max), adminOnline === '' ? undefined : Number(adminOnline)), out => `Saved: ${out.max} climbers max, ${out.online} bookable online.`) }
  const createFaq = async e => { e.preventDefault(); if (!newFaq.q || !newFaq.a) return setMsg({ type:'err', text:'Enter a question and answer.' }); if (await run(() => adminService.addFaq(newFaq.q, newFaq.a), 'FAQ added.')) setNewFaq({ q:'', a:'' }) }
  const createEvent = async e => { e.preventDefault(); if (!newEventName.trim()) return setMsg({ type:'err', text:'Event name required.' }); if (await run(() => adminService.addEvent({ ...EMPTY_EVENT, name: newEventName.trim() }), 'Event added.')) setNewEventName('') }
  const patchAppt = (id, patch) => run(() => bookingService.update(id, patch), out => `Updated ${out.name} — ${out.status || 'confirmed'}`)

  return (
    <>
      <div className="page-intro mt"><h2>Admin portal</h2><p>Manage capacity, content, events, and reservations.</p></div>
      {msg && <p className={`note ${msg.type} mt14`}>{msg.text}</p>}

      <section className="tile mt14">
        <div className="tile-head"><h2>Site content</h2></div>
        <div className="tile-body">
          <form className="stack" onSubmit={saveContent}>
            {CONTENT_FIELDS.map(key => (
              <div className="field plain" key={key}>
                <label htmlFor={`sc-${key}`}>{key.replace('_', ' ')}</label>
                <input id={`sc-${key}`} className="input" value={draft[key] || ''} onChange={e => setDraft(d => ({ ...d, [key]: e.target.value }))} placeholder={PLACEHOLDERS[key]} />
              </div>
            ))}
            <button className="btn btn-primary self-start">Save content</button>
          </form>
        </div>
      </section>

      <section className="tile rise mt">
        <div className="tile-head"><h2>Classes</h2></div>
        <div className="tile-body">
          {data.events.map(ev => (
            <div key={ev.id} className="list-row">
              <span className="grow fw600">{ev.name}</span>
              <Chip cls={ev.spots_filled >= ev.spots_total ? 'c-warn' : 'c-ok'}>{ev.spots_filled}/{ev.spots_total}</Chip>
              <button className="btn btn-sm" onClick={async () => { const name = prompt('New name', ev.name); if (name && name.trim() && name !== ev.name) await run(() => adminService.renameEvent(ev.id, name.trim())) }}>Rename</button>
              <button className="btn btn-ghost btn-sm" onClick={() => run(() => adminService.removeEvent(ev.id))}>Remove</button>
            </div>
          ))}
          <form className="row add-form" onSubmit={createEvent}>
            <div className="field grow plain"><label>New class name</label><input className="input" value={newEventName} onChange={e => setNewEventName(e.target.value)} placeholder="Intro to Bouldering" /></div>
            <button className="btn btn-primary">Add class</button>
          </form>
        </div>
      </section>

      <section className="tile mt14">
        <div className="tile-head"><h2>Capacity</h2><span className="muted small">{data.capacity.active} at the wall now</span></div>
        <div className="tile-body">
          <form className="row" onSubmit={saveCapacity}>
            <div className="field grow plain"><label htmlFor="admin-max">Max climbers</label><input id="admin-max" className="input" type="number" min={1} max={200} placeholder={String(data.capacity.max)} value={adminMax} onChange={e => setAdminMax(e.target.value)} /></div>
            <div className="field grow plain"><label htmlFor="admin-online">Bookable online</label><input id="admin-online" className="input" type="number" min={0} max={200} placeholder={String(data.capacity.online ?? '')} value={adminOnline} onChange={e => setAdminOnline(e.target.value)} /></div>
            <button className="btn btn-primary">Save</button>
          </form>
        </div>
      </section>

      <HoursAdmin onChanged={onDataChanged} />

      <section className="tile rise mt">
        <div className="tile-head"><h2>Reservations</h2></div>
        <div className="tile-body">
          {data.appointments.length === 0 ? <p className="event-meta">No reservations yet.</p> : (
            <ul className="events">
              {data.appointments.map(a => (
                <li key={a.id} className="event-row top">
                  {editing?.id === a.id ? (
                    <form className="stack grow" onSubmit={async e => { e.preventDefault(); if (await patchAppt(a.id, { name: editing.name, date: editing.date, time: editing.time, departure: editing.departure })) setEditing(null) }}>
                      <div className="row2">
                        <div className="field plain"><label>Name</label><input className="input" value={editing.name} onChange={e => setEditing(f => ({ ...f, name: e.target.value }))} /></div>
                        <div className="field plain"><label>Date</label><input className="input" type="date" value={editing.date} onChange={e => setEditing(f => ({ ...f, date: e.target.value }))} /></div>
                      </div>
                      <div className="row2">
                        <div className="field plain"><label>Arrive</label><select className="select" value={editing.time} onChange={e => setEditing(f => ({ ...f, time: e.target.value }))}>{TIMES.map(t => <option key={t}>{t}</option>)}</select></div>
                        <div className="field plain"><label>Leave</label><select className="select" value={editing.departure} onChange={e => setEditing(f => ({ ...f, departure: e.target.value }))}>{TIMES.map(t => <option key={t}>{t}</option>)}</select></div>
                      </div>
                      <div className="row"><button className="btn btn-primary">Save</button><button type="button" className="btn" onClick={() => setEditing(null)}>Cancel</button></div>
                    </form>
                  ) : (
                    <>
                      <div className="event-main"><span className="fw600">{a.name}</span> <span className="mono">{a.code}</span><div className="event-meta">{a.date} · {fmtWindow(a.time, a.departure)}{a.email ? ` · ${a.email}` : ''}</div></div>
                      <Chip cls={a.status === 'cancelled' ? 'c-err' : a.status === 'pending' ? 'c-warn' : 'c-ok'}>{a.status || 'confirmed'}</Chip>
                    </>
                  )}
                  {editing?.id !== a.id && (
                    <div className="row btn-row">
                      <button className="btn btn-sm" onClick={() => setEditing({ id: a.id, name: a.name, date: a.date, time: a.time, departure: a.departure })}>Edit</button>
                      {a.status !== 'confirmed' && <button className="btn btn-sm" onClick={() => patchAppt(a.id, { status:'confirmed' })}>Confirm</button>}
                      {a.status !== 'cancelled' && <button className="btn btn-sm" onClick={() => patchAppt(a.id, { status:'cancelled' })}>Cancel</button>}
                      <button className="btn btn-ghost btn-sm" onClick={() => run(() => bookingService.remove(a.id))}>Delete</button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <section className="tile rise mt">
        <div className="tile-head"><h2>FAQ editor</h2></div>
        <div className="tile-body">
          {data.faqs.map(f => (
            <div key={f.id} className="list-row top">
              <span className="grow"><b>{f.q}</b><div className="faq-answer">{f.a}</div></span>
              <button className="btn btn-ghost btn-sm" onClick={() => run(() => adminService.removeFaq(f.id))}>Remove</button>
            </div>
          ))}
          <form className="stack add-form" onSubmit={createFaq}>
            <div className="field plain"><label>Question</label><input className="input" value={newFaq.q} onChange={e => setNewFaq(s => ({ ...s, q: e.target.value }))} placeholder="What are the hours?" /></div>
            <div className="field plain"><label>Answer</label><input className="input" value={newFaq.a} onChange={e => setNewFaq(s => ({ ...s, a: e.target.value }))} placeholder="Open 3–8 PM." /></div>
            <button className="btn btn-primary self-start">Add FAQ</button>
          </form>
        </div>
      </section>
    </>
  )
}
