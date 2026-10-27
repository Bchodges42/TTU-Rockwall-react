import { useState } from 'react'
import BookingCard from './BookingCard.jsx'
import { feedbackService } from '../services/rockwallService.js'
import { fmtTime } from '../services/format.js'

const EVENT_LINK = 'https://recreation.tntech.edu/program?classificationId=41963321-bd55-41c8-af8e-cd07559ba06b'
const EMPTY_FB = { route: '', rating: 5, comment: '', author: '' }

// MainPage = Home + "Gear & FAQ" (the public site). Status is shown once, in the hero;
// sections here carry plain titles and only flag things a climber needs to act on.
export default function MainPage({ page, data, user, onFind, onDataChanged }) {
  const [faqOpen, setFaqOpen] = useState(null)
  const [fbForm, setFbForm] = useState(EMPTY_FB)
  const [fbMsg, setFbMsg] = useState(null)

  if (page !== 'home' && page !== 'more') return null

  async function sendFeedback(e) {
    e.preventDefault()
    if (!fbForm.route || !fbForm.comment) return setFbMsg({ type:'err', text:'Pick a route and leave a comment.' })
    try { await feedbackService.create(fbForm); setFbForm(EMPTY_FB); setFbMsg({ type: 'ok', text: 'Thanks for the feedback!' }); onDataChanged() }
    catch (error) { setFbMsg({ type:'err', text:error.message }) }
  }
  const setF = key => e => setFbForm(f => ({ ...f, [key]: key === 'rating' ? Number(e.target.value) : e.target.value }))

  if (page === 'home') {
    const { capacity, events, leaderboard, peak } = data
    return (
      <>
        <BookingCard hours={data.hours} user={user} onBooked={onDataChanged} onFind={onFind} />

        <div className="tile-grid">
          <section className="tile">
            <div className="tile-head"><h2>At the wall now</h2></div>
            <div className="tile-body"><CapacityBody capacity={capacity} /></div>
          </section>

          <section className="tile">
            <div className="tile-head"><h2>Classes &amp; events</h2></div>
            <div className="tile-body">
              <ul className="events">
                {events.length === 0 && <li className="event-meta">No classes scheduled.</li>}
                {events.map((ev, i) => <EventRow key={ev.id ?? i} ev={ev} />)}
              </ul>
              <a className="tile-link" href={EVENT_LINK} target="_blank" rel="noreferrer">Campus class registration ↗</a>
            </div>
          </section>
        </div>

        {leaderboard.length > 0 && <Leaderboard leaderboard={leaderboard} />}
        {peak.some(p => p.count > 0) && <PeakTimes peak={peak} hours={data.hours} />}
      </>
    )
  }

  // Gear & FAQ
  const flagged = data.equipment.filter(eq => !/available|free/i.test(eq.status || ''))
  return (
    <>
      <div className="page-intro"><h2>Gear &amp; FAQ</h2><p>What's on hand, what climbers are saying, and quick answers.</p></div>

      <section className="tile mt14">
        <div className="tile-head"><h2>Equipment</h2></div>
        <div className="tile-body">
          {data.equipment.length > 0 && flagged.length === 0 && <p className="tile-lede">Everything below is free to use. Ask the desk for your size.</p>}
          <ul className="events">
            {data.equipment.length === 0 && <li className="event-meta">Shoes, harnesses and chalk are available at the desk.</li>}
            {data.equipment.map(eq => (
              <li className="event-row" key={eq.id}>
                <div className="event-main"><span className="fw600">{eq.name}</span>{eq.note && <div className="event-meta">{eq.note}</div>}</div>
                {flagged.includes(eq) && <span className={`flag ${/limited/i.test(eq.status) ? 'warn' : 'err'}`}>{eq.status}</span>}
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="tile mt">
        <div className="tile-head"><h2>Route feedback</h2></div>
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
          {data.feedback.length > 0 && (
            <ul className="events">
              {data.feedback.map(fb => (
                <li className="event-row" key={fb.id}>
                  <div className="event-main">
                    <span className="fw600">{fb.route}</span>{' '}
                    <span className="event-meta inline">· <span aria-label={`${fb.rating} of 5 stars`}>{'★'.repeat(fb.rating)}{'☆'.repeat(5-fb.rating)}</span> · {fb.author}</span>
                    <div className="event-meta fb-comment">{fb.comment}</div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      {data.faqs.length > 0 && (
        <section className="tile mt">
          <div className="tile-head"><h2>FAQ</h2></div>
          <div className="tile-body">
            <div className="faq-list">
              {data.faqs.map(f => (
                <div key={f.id} className="faq-row">
                  <button className={`faq-q ${faqOpen===f.id?'on':''}`} onClick={() => setFaqOpen(o => o===f.id?null:f.id)} aria-expanded={faqOpen===f.id}>
                    <span>{f.q}</span><span className="faq-plus" aria-hidden="true">{faqOpen===f.id?'–':'+'}</span>
                  </button>
                  {faqOpen===f.id && <p className="faq-a">{f.a}</p>}
                </div>
              ))}
            </div>
          </div>
        </section>
      )}
    </>
  )
}

function pctOf(capacity) {
  return capacity.max ? Math.min(100, Math.round((capacity.active / capacity.max) * 100)) : 0
}

function EventRow({ ev }) {
  const left = ev.spots_total - ev.spots_filled
  return (
    <li className="event-row">
      <div className="event-main">
        <a href={ev.link || EVENT_LINK} target="_blank" rel="noreferrer">{ev.name}</a>
        {ev.next_date && <div className="event-meta">{ev.next_date}</div>}
      </div>
      {left > 0 ? <span className="event-meta">{left} of {ev.spots_total} spots left</span> : <span className="flag err">Full</span>}
    </li>
  )
}

function CapacityBody({ capacity }) {
  const pct = pctOf(capacity)
  const capCls = capacity.active >= capacity.max ? 'full' : pct >= 70 ? 'tight' : ''
  return (
    <>
      <div className="cap-big"><span className="n">{capacity.active}</span><span className="of">of <b>{capacity.max}</b> climbing</span></div>
      <div className={`cap-track ${capCls}`} role="progressbar" aria-valuenow={capacity.active} aria-valuemin={0} aria-valuemax={capacity.max} aria-label="Climbers at the wall"><span style={{ width: `${pct}%` }} /></div>
      <p className="tile-note">Walk-ins are welcome while there's room. Booking holds you an online space.</p>
    </>
  )
}

function Leaderboard({ leaderboard }) {
  return (
    <section className="tile mt">
      <div className="tile-head"><h2>Leaderboard</h2></div>
      <div className="tile-body">
        <ol className="board">
          {leaderboard.map((r, i) => (
            <li key={r.id} className="board-row">
              <span className="board-rank">{i + 1}</span>
              <span className="board-name">{r.name}</span>
              <span className="board-score">{r.score}</span>
            </li>
          ))}
        </ol>
      </div>
    </section>
  )
}

function PeakTimes({ peak, hours }) {
  const today = hours?.today
  const shown = today?.open ? peak.filter(p => p.hour >= Number(today.opens.slice(0, 2)) && p.hour < Number(today.closes.slice(0, 2))) : peak
  const rows = shown.length ? shown : peak
  const max = Math.max(1, ...rows.map(p => p.count))
  const nowHour = new Date().getHours()
  return (
    <section className="tile mt">
      <div className="tile-head"><h2>Busiest hours</h2></div>
      <div className="tile-body">
        <div className="peak-bars" aria-label="Check-ins by hour">
          {rows.map(p => (
            <div className={`peak-col ${p.hour === nowHour ? 'now' : ''}`} key={p.hour}>
              <span className="peak-count">{p.count}</span>
              <div className="peak-track"><span style={{ height: `${Math.round((p.count / max) * 100)}%` }} /></div>
              <span className="peak-label">{fmtTime(`${String(p.hour).padStart(2, '0')}:00`)}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
