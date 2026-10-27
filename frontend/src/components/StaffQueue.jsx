import { useEffect, useRef, useState } from 'react'
import { queueService } from '../services/rockwallService.js'
import { fmtWindow } from '../services/format.js'

export default function StaffQueue({ onDataChanged }) {
  const [entries, setEntries] = useState([])
  const [receipt, setReceipt] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function load() {
    try { setEntries(await queueService.list()); setError('') }
    catch (err) { setError(err.message) }
  }
  useEffect(() => {
    load()
    const timer = setInterval(load, 15000)
    return () => clearInterval(timer)
  }, [])

  async function run(action) {
    setBusy(true)
    try {
      await action()
      await load()
      onDataChanged()
      return true
    } catch (err) { setError(err.message); return false }
    finally { setBusy(false) }
  }

  async function addWalkin(event) {
    event.preventDefault()
    const parts = name.trim().split(/\s+/)
    if (await run(() => queueService.add({ firstname: parts[0] || 'Guest', lastname: parts.slice(1).join(' ') }))) setName('')
  }

  return (
    <>
      <CheckInDesk onCheckedIn={() => { load(); onDataChanged() }} />
      <section className="tile mt14">
        <div className="tile-head"><h2>Visitor queue</h2></div>
        <div className="tile-body stack">
          {error && <p className="note err" role="alert">{error}</p>}
          <form className="row" onSubmit={addWalkin}>
            <div className="field grow plain"><label htmlFor="walkin-name">Walk-in name (optional)</label>
              <input id="walkin-name" className="input" value={name} onChange={e => setName(e.target.value)} /></div>
            <button className="btn" disabled={busy}>Add walk-in</button>
          </form>
          <form className="row" onSubmit={async event => {
            event.preventDefault()
            if (await run(() => queueService.add({ receipt: receipt.trim() }))) setReceipt('')
          }}>
            <div className="field grow plain"><label htmlFor="queue-receipt">Add a booking to the queue without checking in</label>
              <input id="queue-receipt" className="input mono" required placeholder="Code or receipt" value={receipt} onChange={e => setReceipt(e.target.value)} /></div>
            <button className="btn" disabled={busy}>Add to queue</button>
          </form>
          {entries.length === 0 && <p className="muted">No visitors waiting or checked in.</p>}
          {entries.map(entry => (
            <div className="list-row" key={entry.id}>
              <span className="grow">{entry.firstname} {entry.lastname} · {entry.kind} · {entry.status}</span>
              {entry.status === 'waiting' ? <>
                <button className="btn btn-sm" disabled={busy} onClick={() => run(() => queueService.change(entry.id, 'admit'))}>Check in</button>
                <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => run(() => queueService.change(entry.id, 'cancel'))}>Remove</button>
              </> : <button className="btn btn-sm" disabled={busy} onClick={() => run(() => queueService.change(entry.id, 'checkout'))}>Check out</button>}
            </div>
          ))}
        </div>
      </section>
    </>
  )
}

// One field for the whole desk flow. A USB QR/barcode scanner acts as a keyboard: it types the
// code and presses Enter, so it works here with no setup. The field refocuses after every check-in.
function CheckInDesk({ onCheckedIn }) {
  const [code, setCode] = useState('')
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [scanning, setScanning] = useState(false)
  const input = useRef(null)
  const canScan = typeof window !== 'undefined' && 'BarcodeDetector' in window && navigator.mediaDevices?.getUserMedia

  useEffect(() => { input.current?.focus() }, [])

  async function checkIn(value) {
    if (!value.trim() || busy) return
    setBusy(true)
    try {
      const out = await queueService.checkIn(value)
      setResult({ ok: true, text: `${out.name} checked in`, detail: `${fmtWindow(out.time, out.departure)} · ${out.active} of ${out.max} at the wall` })
      onCheckedIn()
    } catch (err) { setResult({ ok: false, text: err.message }) }
    finally { setBusy(false); setCode(''); input.current?.focus() }
  }

  return (
    <section className="tile mt14 desk">
      <div className="tile-head"><h2>Check in</h2>{canScan && <button type="button" className="btn btn-sm" onClick={() => setScanning(s => !s)}>{scanning ? 'Stop camera' : 'Scan with camera'}</button>}</div>
      <div className="tile-body">
        <form className="row" onSubmit={e => { e.preventDefault(); checkIn(code) }}>
          <div className="field grow plain"><label htmlFor="desk-code">Code</label>
            <input id="desk-code" ref={input} className="input mono code-input" autoComplete="off" autoCapitalize="characters" spellCheck="false"
              placeholder="Type or scan" value={code} onChange={e => setCode(e.target.value)} /></div>
          <button className="btn btn-primary" disabled={busy}>Check in</button>
        </form>
        {scanning && <CameraScanner onCode={value => { setScanning(false); checkIn(value) }} />}
        {result && <p className={`note ${result.ok ? 'ok' : 'err'} mt14`} role="status"><b>{result.text}</b>{result.detail && <> · {result.detail}</>}</p>}
      </div>
    </section>
  )
}

function CameraScanner({ onCode }) {
  const video = useRef(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let stream, timer, stopped = false
    const detector = new window.BarcodeDetector({ formats: ['qr_code'] })
    navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } }).then(s => {
      stream = s
      if (stopped) return s.getTracks().forEach(t => t.stop())
      video.current.srcObject = s
      video.current.play()
      timer = setInterval(async () => {
        const [hit] = await detector.detect(video.current).catch(() => [])
        if (hit?.rawValue) { clearInterval(timer); onCode(hit.rawValue) }
      }, 250)
    }).catch(() => setError('Camera unavailable. Type the code instead.'))
    return () => { stopped = true; clearInterval(timer); stream?.getTracks().forEach(t => t.stop()) }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  return error ? <p className="note err mt14">{error}</p> : <video ref={video} className="scanner" muted playsInline />
}
