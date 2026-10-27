import { useEffect, useState } from 'react'
import { bookingService } from '../services/rockwallService.js'
import { fmtDay, fmtWindow } from '../services/format.js'
import { CodeBoxes } from './BookingCard.jsx'

// Landing page for the "Manage or cancel" link in the confirmation email (/booking#token=…).
// Opening the link only shows the booking; cancelling takes a deliberate second click.
export default function ManageBooking({ token, onHome }) {
  const [booking, setBooking] = useState(null)
  const [error, setError] = useState('')
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!token) { setError('This link is missing its booking token.'); return }
    bookingService.manage(token).then(setBooking).catch(e => setError(e.message))
  }, [token])

  async function cancel() {
    setBusy(true)
    try { setBooking({ ...(await bookingService.cancelByToken(token)).appointment, can_cancel: false }); setConfirming(false) }
    catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }

  const cancelled = booking?.status === 'cancelled'
  return (
    <section className="booker manage rise">
      {error && <p className="note err" role="alert">{error}</p>}
      {!booking && !error && <p className="muted">Loading your booking…</p>}
      {booking && (
        <>
          <p className="eyebrow">{cancelled ? 'Booking cancelled' : booking.status === 'confirmed' ? 'Your booking' : `Booking ${booking.status}`}</p>
          <h2 className={cancelled ? 'struck' : ''}>{fmtDay(booking.date)}<br />{fmtWindow(booking.time, booking.departure)}</h2>
          <p className="muted">{booking.name}</p>
          {!cancelled && booking.code && <><CodeBoxes code={booking.code} /><p className="muted small">Show this code at the desk.</p></>}
          {cancelled && <p className="note ok">Your space has been released. Thanks for letting us know. We emailed you a confirmation.</p>}
          <div className="row mt14">
            {booking.can_cancel && !confirming && <button className="btn" onClick={() => setConfirming(true)}>Cancel this booking</button>}
            {confirming && <>
              <button className="btn btn-danger" disabled={busy} onClick={cancel}>{busy ? 'Cancelling…' : 'Yes, cancel it'}</button>
              <button className="btn btn-ghost" onClick={() => setConfirming(false)}>Keep my booking</button>
            </>}
            {!confirming && <button className="btn btn-primary" onClick={onHome}>{cancelled ? 'Book another time' : 'Go to the Rockwall site'}</button>}
          </div>
        </>
      )}
    </section>
  )
}
