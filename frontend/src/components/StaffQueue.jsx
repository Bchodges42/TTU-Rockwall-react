import { useEffect, useState } from 'react'
import { queueService } from '../services/rockwallService.js'

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
    <section className="tile mt14">
      <div className="tile-head"><h2>Visitor queue and check-in</h2></div>
      <div className="tile-body stack">
        {error && <p className="note err" role="alert">{error}</p>}
        <form className="row" onSubmit={async event => {
          event.preventDefault()
          if (await run(() => queueService.add({ receipt: receipt.trim() }))) setReceipt('')
        }}>
          <div className="field grow plain"><label htmlFor="queue-receipt">Reservation receipt</label>
            <input id="queue-receipt" className="input" required value={receipt} onChange={e => setReceipt(e.target.value)} /></div>
          <button className="btn btn-primary" disabled={busy}>Add reservation</button>
        </form>
        <form className="row" onSubmit={addWalkin}>
          <div className="field grow plain"><label htmlFor="walkin-name">Walk-in name (optional)</label>
            <input id="walkin-name" className="input" value={name} onChange={e => setName(e.target.value)} /></div>
          <button className="btn" disabled={busy}>Add walk-in</button>
        </form>
        {entries.length === 0 && <p>No visitors waiting or checked in.</p>}
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
  )
}
