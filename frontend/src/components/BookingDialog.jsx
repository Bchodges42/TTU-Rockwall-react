import { useEffect, useRef, useState } from 'react'
import { bookingService } from '../services/rockwallService.js'

const EMPTY_APPT = { name: '', date: '', time: '' }

// Book a visit: availability check, booking form + receipt, receipt verification.
export default function BookingDialog({ tab, setTab, onClose, onDataChanged }) {
  const [appt, setAppt] = useState(EMPTY_APPT)
  const [receipt, setReceipt] = useState(null)
  const [lookupId, setLookupId] = useState('')
  const [msg, setMsg] = useState(null)
  const ref = useRef(null)

  useEffect(() => {
    ref.current?.querySelector('input, button:not(.dlg-close)')?.focus()
    const onKey = e => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const set = key => e => setAppt(a => ({ ...a, [key]: e.target.value }))

  async function run(action, okText) {
    try {
      const data = await action()
      setMsg({ type: 'ok', text: typeof okText === 'function' ? okText(data) : (data.message || okText) })
      return data
    } catch (error) { setMsg({ type: 'err', text: error.message }) }
  }

  async function checkAvail(e) {
    e.preventDefault()
    if (!e.target.elements.date.value) return setMsg({ type: 'err', text: 'Pick a date first.' })
    run(() => bookingService.availability(e.target.elements.date.value))
  }
  async function book(e) {
    e.preventDefault()
    if (!appt.name || !appt.date || !appt.time) return setMsg({ type: 'err', text: 'Name, date, and time are required.' })
    const data = await run(() => bookingService.create(appt))
    if (!data) return
    setReceipt(data.receipt || data.appointment?.id || null)
    setAppt(EMPTY_APPT)
    onDataChanged()
  }
  async function verify() {
    const id = (lookupId || receipt || '').trim()
    if (!id) return setMsg({ type: 'err', text: 'Enter a receipt number.' })
    run(
      () => bookingService.verify(id),
      data => `Verified${data.status ? ` · ${data.status}` : ''}: ${data.name} · ${data.date} ${data.time} (receipt ${data.id.slice(0,8)}…)`,
    )
  }

  return (
    <div className="overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="dialog dialog-wide rise" ref={ref} role="dialog" aria-labelledby="db-h">
        <button type="button" className="dlg-close" onClick={onClose} aria-label="Close">×</button>
        <h2 id="db-h">Book a visit</h2>
        <p className="sub">Check a date, or lock in priority access.</p>
        <div className="seg" role="tablist" aria-label="Section">
          <button role="tab" aria-selected={tab==='availability'} className={tab==='availability'?'on':''} onClick={() => { setTab('availability'); setMsg(null) }}>Availability</button>
          <button role="tab" aria-selected={tab==='schedule'} className={tab==='schedule'?'on':''} onClick={() => { setTab('schedule'); setMsg(null) }}>Book</button>
        </div>
        {msg && <p className={`note ${msg.type}`}>{msg.text}</p>}
        {tab==='availability' && (
          <form onSubmit={checkAvail}>
            <div className="field"><label htmlFor="av-date">Date</label><input id="av-date" className="input" type="date" name="date" /></div>
            <button className="btn btn-primary btn-block">Check availability</button>
          </form>
        )}
        {tab==='schedule' && (
          <>
            {receipt && (
              <div className="receipt rise">
                <div className="receipt-head">Booking confirmed ✓</div>
                <code className="receipt-id">{receipt}</code>
                <div className="receipt-sub">Show this receipt at the desk to verify your slot.</div>
                <div className="row">
                  <button type="button" className="btn" onClick={() => navigator.clipboard.writeText(receipt)}>Copy number</button>
                  <button type="button" className="btn btn-ghost" onClick={() => { setReceipt(null); setMsg(null) }}>Book another</button>
                </div>
              </div>
            )}
            <form onSubmit={book} style={{ marginTop: receipt ? 14 : 0 }}>
              <div className="field"><label htmlFor="bk-name">Full name <span className="req">*</span></label><input id="bk-name" className="input" value={appt.name} onChange={set('name')} placeholder="First and last" /></div>
              <div className="row2">
                <div className="field"><label htmlFor="bk-date">Date <span className="req">*</span></label><input id="bk-date" className="input" type="date" value={appt.date} onChange={set('date')} /></div>
                <div className="field"><label htmlFor="bk-time">Time <span className="req">*</span></label><input id="bk-time" className="input" type="time" value={appt.time} onChange={set('time')} /></div>
              </div>
              <button className="btn btn-warm btn-block">Book appointment</button>
            </form>
            <div className="row verify-row">
              <div className="field grow plain"><label htmlFor="verify-id">Verify receipt</label><input id="verify-id" className="input" placeholder="Paste receipt number" value={lookupId} onChange={e => setLookupId(e.target.value)} /></div>
              <button type="button" className="btn" onClick={verify}>Verify</button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
