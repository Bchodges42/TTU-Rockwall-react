import { useEffect, useRef, useState } from 'react'
import { bookingService } from '../services/rockwallService.js'
import { fmtDay, fmtWindow } from '../services/format.js'

// Signed-in climbers see and cancel their bookings; anyone can look one up by its 4-character code.
export default function BookingDialog({ user, onClose, onDataChanged }) {
  const [mine, setMine] = useState(null)
  const [lookup, setLookup] = useState('')
  const [found, setFound] = useState(null)
  const [confirming, setConfirming] = useState(null)
  const [msg, setMsg] = useState(null)
  const ref = useRef(null)

  async function loadMine() {
    if (!user) return
    try { setMine(await bookingService.mine()) } catch (error) { setMsg({ type: 'err', text: error.message }) }
  }
  useEffect(() => { loadMine() }, [user]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    ref.current?.querySelector('input, button:not(.dlg-close)')?.focus()
    const onKey = e => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  async function cancel(booking) {
    try {
      await bookingService.cancel(booking.id)
      setConfirming(null)
      setMsg({ type: 'ok', text: `Cancelled ${fmtDay(booking.date, 'short')}. A confirmation email is on its way.` })
      await loadMine(); onDataChanged()
    } catch (error) { setMsg({ type: 'err', text: error.message }) }
  }
  async function find(e) {
    e.preventDefault()
    if (!lookup.trim()) return
    try { setFound(await bookingService.verify(lookup.trim())); setMsg(null) }
    catch (error) { setFound(null); setMsg({ type: 'err', text: error.message }) }
  }

  const upcoming = (mine || []).filter(b => b.status === 'confirmed' || b.status === 'pending')
  const past = (mine || []).filter(b => !upcoming.includes(b))

  return (
    <div className="overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="dialog dialog-wide rise" ref={ref} role="dialog" aria-labelledby="mb-h">
        <button type="button" className="dlg-close" onClick={onClose} aria-label="Close">×</button>
        <h2 id="mb-h">{user ? 'My bookings' : 'Find my booking'}</h2>
        <p className="sub">{user ? 'Cancel anything you can no longer make so someone else can climb.' : 'Lost your email? Look a booking up by its 4-character code.'}</p>
        {msg && <p className={`note ${msg.type}`} role="status">{msg.text}</p>}

        {user && (
          <ul className="booking-list">
            {mine && !mine.length && <li className="muted">No bookings yet.</li>}
            {upcoming.map(b => (
              <li key={b.id}>
                <div className="grow">
                  <b>{fmtDay(b.date, 'short')} · {fmtWindow(b.time, b.departure)}</b>
                  <div className="muted small">Code <span className="mono">{b.code || '—'}</span>{b.status === 'pending' ? ' · awaiting staff confirmation' : ''}</div>
                </div>
                {confirming === b.id
                  ? <><button className="btn btn-sm btn-danger" onClick={() => cancel(b)}>Yes, cancel</button><button className="btn btn-sm btn-ghost" onClick={() => setConfirming(null)}>Keep</button></>
                  : <button className="btn btn-sm" onClick={() => setConfirming(b.id)}>Cancel</button>}
              </li>
            ))}
            {past.map(b => (
              <li key={b.id} className="past">
                <div className="grow"><span>{fmtDay(b.date, 'short')} · {fmtWindow(b.time, b.departure)}</span></div>
                <span className="muted small">{b.status}</span>
              </li>
            ))}
          </ul>
        )}

        <form className="row verify-row" onSubmit={find}>
          <div className="field grow plain"><label htmlFor="lookup">Check-in code</label>
            <input id="lookup" className="input mono" maxLength={40} placeholder="e.g. K7QX" value={lookup} onChange={e => setLookup(e.target.value)} /></div>
          <button className="btn">Look up</button>
        </form>
        {found && (
          <p className="note mt14">
            <b>{fmtDay(found.date)} · {fmtWindow(found.time, found.departure)}</b><br />
            {found.name} · {found.status}
          </p>
        )}
      </div>
    </div>
  )
}
