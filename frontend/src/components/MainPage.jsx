import { useState } from 'react'
import { Chip } from './Chip.jsx'
import { eqClass, eventStatus } from '../services/eventService.js'
import { feedbackService } from '../services/rockwallService.js'

const EVENT_LINK = 'https://recreation.tntech.edu/program?classificationId=41963321-bd55-41c8-af8e-cd07559ba06b'
const EMPTY_FB = { route: '', rating: 5, comment: '', author: '' }

// MainPage = Home + More content (the public site)
export default function MainPage({ page, data, isAdmin, setPage, onBook, onDataChanged }) {
  const [faqOpen, setFaqOpen] = useState(null)
  const [fbForm, setFbForm] = useState(EMPTY_FB)
  const [fbMsg, setFbMsg] = useState(null)

  if (page !== 'home' && page !== 'more') return null

  async function sendFeedback(e) {
    e.preventDefault()
    if (!fbForm.route || !fbForm.comment) return setFbMsg({ type:'err', text:'Pick a route and leave a comment.' })
    try { await feedbackService.create(fbForm); setFbForm(EMPTY_FB); setFbMsg(null); onDataChanged() }
    catch (error) { setFbMsg({ type:'err', text:error.message }) }
  }
  const setF = key => e => setFbForm(f => ({ ...f, [key]: key === 'rating' ? Number(e.target.value) : e.target.value }))

  if (page === 'home') {
    const { capacity, events, leaderboard, peak } = data
    const peakMax = peak.length ? Math.max(...peak.map(p => p.count)) : 1
    return (
      <>
        <div className="tile-grid">
          <section className="tile rise">
            <div className="tile-head"><h2>Priority access</h2>{isAdmin ? <Chip cls="c-accent">Admin</Chip> : <StatusChip capacity={capacity} />}</div>
            <div className="tile-body">
              <CapacityBody capacity={capacity} />
              <p className="tile-note">Reserve a slot when it's busy — hop the queue with a booked time.</p>
            </div>
            <div className="tile-foot row">
              <button className="btn btn-warm grow" onClick={() => onBook('schedule')}>Book a slot</button>
              {isAdmin && <button className="btn" onClick={() => setPage('admin')}>Open admin</button>}
            </div>
          </section>

          <section className="tile rise">
            <div className="tile-head"><h2>Classes & events</h2><Chip cls="c-info">{events.length} today</Chip></div>
            <div className="tile-body">
              <ul className="events">
                {events.length === 0 && <li className="event-meta">Loading…</li>}
                {events.map((ev, i) => (
                  <EventRow key={ev.id ?? i} ev={ev} st={eventStatus(ev)} showOpen />
                ))}
              </ul>
            </div>
            <div className="tile-foot"><button className="btn btn-block" onClick={() => onBook('availability')}>Check availability</button></div>
          </section>
        </div>

        <Leaderboard leaderboard={leaderboard} />
        <PeakTimes peak={peak} peakMax={peakMax} />
      </>
    )
  }

  // more
  return (
    <>
      <div className="page-intro"><h2>More from the wall</h2><p>Gear on hand, what climbers are saying, and quick answers.</p></div>

      <section className="tile rise">
        <div className="tile-head"><h2>Equipment</h2><Chip cls="c-info">{data.equipment.length} items</Chip></div>
        <div className="tile-body">
          <ul className="events">
            {data.equipment.map(eq => (
              <li className="event-row" key={eq.id}>
                <div className="event-main"><span className="fw600">{eq.name}</span><div className="event-meta">{eq.note || '—'}</div></div>
                <Chip cls={eqClass(eq.status)}>{eq.status}</Chip>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="tile rise mt">
        <div className="tile-head"><h2>Route feedback</h2><Chip cls="c-info">{data.feedback.length} notes</Chip></div>
        <div className="tile-body">
          <form className="stack fb-form" onSubmit={sendFeedback}>
            <div className="row2">
              <div className="field plain"><label htmlFor="fb-route">Route</label><select id="fb-route" className="select" value={fbForm.route} onChange={setF('route')}><option value="">Select a route</option>{data.routes.map(r => <option key={r.id} value={r.name}>{r.name} — {r.grade}</option>)}</select></div>
              <div className="field plain"><label htmlFor="fb-rating">Rating</label><select id="fb-rating" className="select" value={fbForm.rating} onChange={setF('rating')}><option value={5}>★★★★★</option><option value={4}>★★★★</option><option value={3}>★★★</option><option value={2}>★★</option><option value={1}>★</option></select></div>
            </div>
            <div className="field plain"><label htmlFor="fb-author">Name (optional)</label><input id="fb-author" className="input" value={fbForm.author} onChange={setF('author')} placeholder="Anonymous" /></div>
            <div className="field plain"><label htmlFor="fb-comment">Comment</label><textarea id="fb-comment" className="input" rows={2} value={fbForm.comment} onChange={setF('comment')} placeholder="How was the route?" /></div>
            {fbMsg && <p className={`note ${fbMsg.type} plain`}>{fbMsg.text}</p>}
            <button className="btn btn-primary self-start">Post feedback</button>
          </form>
          <ul className="events">
            {data.feedback.length === 0 && <li className="event-meta">No feedback yet — be the first.</li>}
            {data.feedback.map(fb => (
              <li className="event-row" key={fb.id}>
                <div className="event-main">
                  <span className="fw600">{fb.route}</span>{' '}
                  <span className="event-meta inline">· {'★'.repeat(fb.rating)}{'☆'.repeat(5-fb.rating)} · {fb.author}</span>
                  <div className="event-meta fb-comment">{fb.comment}</div>
                </div>
                <Chip cls="c-info">{fb.rating}/5</Chip>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="tile rise mt">
        <div className="tile-head"><h2>FAQ</h2><Chip cls="c-accent">{data.faqs.length} answers</Chip></div>
        <div className="tile-body">
          <div className="stack">
            {data.faqs.map(f => (
              <div key={f.id} className="faq-row">
                <button className={`faq-q ${faqOpen===f.id?'on':''}`} onClick={() => setFaqOpen(o => o===f.id?null:f.id)} aria-expanded={faqOpen===f.id}>
                  <span>{f.q}</span><span className="faq-plus">{faqOpen===f.id?'–':'+'}</span>
                </button>
                {faqOpen===f.id && <p className="faq-a">{f.a}</p>}
              </div>
            ))}
          </div>
        </div>
      </section>
    </>
  )
}

function pctOf(capacity) {
  return capacity.max ? Math.round((capacity.active / capacity.max) * 100) : 0
}

function EventRow({ ev, st }) {
  if (!st) return null
  return (
    <li className="event-row">
      <div className="event-main">
        <a href={ev.link || EVENT_LINK} target="_blank" rel="noreferrer">{ev.name}</a>
        <div className="event-meta">{ev.spots_total - ev.spots_filled} of {ev.spots_total} open</div>
      </div>
      <Chip cls={st.cls}>{st.txt}</Chip>
    </li>
  )
}

function StatusChip({ capacity }) {
  const chip = statusOf(capacity)
  return <Chip cls={chip.cls}>{chip.label}</Chip>
}

function statusOf(capacity) {
  const pct = pctOf(capacity)
  return capacity.active >= capacity.max ? { cls:'c-err', label:'Full' } : pct >= 70 ? { cls:'c-warn', label:'Busy' } : { cls:'c-ok', label:'Open' }
}

function CapacityBody({ capacity }) {
  const pct = pctOf(capacity)
  const capCls = capacity.active >= capacity.max ? 'full' : pct >= 70 ? 'tight' : ''
  return (
    <>
      <div className="cap-big"><span className="n">{capacity.active}</span><span className="of">of <b>{capacity.max}</b> in the wall</span></div>
      <div className={`cap-track ${capCls}`} role="progressbar" aria-valuenow={capacity.active} aria-valuemin={0} aria-valuemax={capacity.max} aria-label="Capacity"><span style={{ width: `${pct}%` }} /></div>
      <div className="cap-foot"><span>{pct}%</span><span>max {capacity.max}</span></div>
    </>
  )
}

function Leaderboard({ leaderboard }) {
  return (
    <section className="tile rise mt">
      <div className="tile-head"><h2>Leaderboard</h2><Chip cls="c-gold">Top sends</Chip></div>
      <div className="tile-body">
        <ol className="board">
          {leaderboard.map((r, i) => (
            <li key={r.id} className="board-row">
              <span className="board-rank">#{i + 1}</span>
              <span className="board-name">{r.name}</span>
              <Chip cls={i === 0 ? 'c-gold' : i === 1 ? 'c-info' : 'c-ok'}>{r.score} pts</Chip>
            </li>
          ))}
        </ol>
      </div>
    </section>
  )
}

function PeakTimes({ peak, peakMax }) {
  return (
    <section className="tile rise mt">
      <div className="tile-head"><h2>Peak-time analytics</h2><Chip cls="c-accent">3 — 8 PM</Chip></div>
      <div className="tile-body">
        <div className="peak-bars" aria-label="Peak visits by hour">
          {peak.map(p => (
            <div className="peak-col" key={p.hour}>
              <div className="peak-track"><span style={{ height: `${Math.round((p.count / peakMax) * 100)}%` }} /></div>
              <span className="peak-label">{p.hour}:00</span>
              <span className="peak-count">{p.count}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
