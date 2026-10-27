import { useEffect, useMemo, useState } from 'react'
import { bookingService } from '../services/rockwallService.js'
import { fmtDay, fmtTime, fmtWindow, relDay } from '../services/format.js'

// The one place to book. Days come from /hours, which already leaves out days the wall is closed.
export default function BookingCard({ hours, user, onBooked, onFind }) {
  const days = hours?.days || []
  const [date, setDate] = useState(null)
  const [slots, setSlots] = useState([])
  const [arrival, setArrival] = useState('')
  const [departure, setDeparture] = useState('')
  const [form, setForm] = useState({ name: '', email: '' })
  const [msg, setMsg] = useState(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(null)

  useEffect(() => { if (user) setForm(f => ({ name: f.name || user.name || '', email: f.email || user.email || '' })) }, [user])
  useEffect(() => {
    if (days.length && !days.some(d => d.date === date)) setDate(days[0].date)
  }, [days, date])
  useEffect(() => {
    if (!date) return
    bookingService.availability(date).then(a => setSlots(a.slots)).catch(() => setSlots([]))
  }, [date, hours])

  const day = days.find(d => d.date === date)
  const bySlot = useMemo(() => Object.fromEntries(slots.map(s => [s.time, s])), [slots])
  // A visit can run until closing or until the first slot with no online spaces left.
  const departures = useMemo(() => {
    const out = []
    for (const slot of slots.filter(s => s.time >= arrival)) {
      if (slot.remaining <= 0) break
      out.push(slot.end)
    }
    return out
  }, [slots, arrival])

  useEffect(() => {
    if (!day) return
    const firstOpen = day.arrivals.find(t => (bySlot[t]?.remaining ?? 1) > 0)
    if (!day.arrivals.includes(arrival) || (bySlot[arrival]?.remaining ?? 1) <= 0) setArrival(firstOpen || '')
  }, [day, bySlot]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!departures.includes(departure)) setDeparture(departures[Math.min(1, departures.length - 1)] || '')
  }, [departures]) // eslint-disable-line react-hooks/exhaustive-deps

  const spaces = departures.length
    ? Math.min(...slots.filter(s => s.time >= arrival && s.time < departure).map(s => s.remaining))
    : 0

  async function book(e) {
    e.preventDefault()
    if (!form.name.trim() || !form.email.trim()) return setMsg('Enter your name and email.')
    setBusy(true); setMsg(null)
    try {
      const out = await bookingService.create({ name: form.name, email: form.email, date, time: arrival, departure })
      setDone(out)
      onBooked()
    } catch (error) { setMsg(error.message) }
    finally { setBusy(false) }
  }

  if (done) return <Confirmation result={done} onAgain={() => setDone(null)} />

  return (
    <section className="booker" id="book" aria-labelledby="book-h">
      <div className="booker-head">
        <h2 id="book-h">Book a time</h2>
        <button type="button" className="btn-quiet" onClick={onFind}>{user ? 'My bookings' : 'Find my booking'}</button>
      </div>
      {!days.length ? (
        <p className="muted">No open days in the next week. <a href="https://www.tntech.edu/recreation/hours.php" target="_blank" rel="noreferrer">Check campus hours ↗</a></p>
      ) : (
        <form onSubmit={book}>
          <div className="day-pills" role="radiogroup" aria-label="Day">
            {days.map(d => (
              <button type="button" key={d.date} role="radio" aria-checked={d.date === date}
                className={d.date === date ? 'on' : ''} onClick={() => setDate(d.date)}>
                <b>{relDay(d.date) === 'today' ? 'Today' : d.weekday.slice(0, 3)}</b>
                <span>{fmtDay(d.date, 'short').split(', ').pop()}</span>
              </button>
            ))}
          </div>
          {day && <p className="muted small">Open {fmtWindow(day.opens, day.closes)} · up to {hours.online_capacity} online climbers at a time</p>}
          <div className="row2">
            <div className="field"><label htmlFor="bk-arrive">Arrive</label>
              <select id="bk-arrive" className="select" value={arrival} onChange={e => setArrival(e.target.value)}>
                {day?.arrivals.map(t => {
                  const left = bySlot[t]?.remaining
                  return <option key={t} value={t} disabled={left === 0}>{fmtTime(t)}{left === 0 ? ' · full' : ''}</option>
                })}
              </select></div>
            <div className="field"><label htmlFor="bk-leave">Leave</label>
              <select id="bk-leave" className="select" value={departure} onChange={e => setDeparture(e.target.value)} disabled={!departures.length}>
                {departures.map(t => <option key={t} value={t}>{fmtTime(t)}</option>)}
              </select></div>
          </div>
          <div className="row2">
            <div className="field"><label htmlFor="bk-name">Name</label>
              <input id="bk-name" className="input" autoComplete="name" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="First and last" /></div>
            <div className="field"><label htmlFor="bk-email">Email</label>
              <input id="bk-email" className="input" type="email" autoComplete="email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} placeholder="name@tntech.edu" /></div>
          </div>
          {msg && <p className="note err" role="alert">{msg}</p>}
          <div className="booker-foot">
            <span className="muted small">{arrival && departures.length ? `${spaces} online ${spaces === 1 ? 'space' : 'spaces'} left for this time. Walk-ins are always welcome while there's room.` : 'That time is full. Try another.'}</span>
            <button className="btn btn-primary" disabled={busy || !departures.length}>{busy ? 'Booking…' : 'Book this time'}</button>
          </div>
        </form>
      )}
    </section>
  )
}

export function CodeBoxes({ code }) {
  return <div className="code-boxes" aria-label={`Check-in code ${code}`}>{[...code].map((c, i) => <span key={i}>{c}</span>)}</div>
}

function Confirmation({ result, onAgain }) {
  const a = result.appointment
  return (
    <section className="booker confirm rise" id="book" aria-live="polite">
      <div className="confirm-grid">
        <div>
          <p className="eyebrow">You're booked</p>
          <h2>{fmtDay(a.date)}<br />{fmtWindow(a.time, a.departure)}</h2>
          <p className="muted">We sent your code, a calendar invite and a cancel link to <b>{result.email}</b>.</p>
          <button type="button" className="btn" onClick={onAgain}>Book another time</button>
        </div>
        <div className="confirm-code">
          <p className="eyebrow">Check-in code</p>
          <CodeBoxes code={result.code} />
          <img src={bookingService.qrUrl(result.code)} alt="" width="132" height="132" />
          <p className="muted small">Show this at the desk.</p>
        </div>
      </div>
    </section>
  )
}
