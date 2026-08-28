import { useEffect, useRef, useState } from 'react'
import { authService } from '../services/rockwallService.js'

const EMPTY = { firstname: '', lastname: '', phone: '', email: '', password: '' }

// Login + register share one form; mode toggles which submit runs.
export default function LoginDialog({ mode, onClose, onSwitch, onSuccess }) {
  const [form, setForm] = useState(EMPTY)
  const [error, setError] = useState('')
  const ref = useRef(null)

  useEffect(() => {
    ref.current?.querySelector('input')?.focus()
    const onKey = e => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const set = key => e => setForm(f => ({ ...f, [key]: e.target.value }))

  async function submit(e) {
    e.preventDefault(); setError('')
    try {
      if (mode === 'login') {
        if (!form.email || !form.password) return setError('Enter your email and password.')
        const data = await authService.login(form.email, form.password)
        setForm(EMPTY)
        onSuccess(data.role)
      } else {
        await authService.register(form)
        setForm(EMPTY)
        onSwitch()
      }
    } catch (err) { setError(err.message) }
  }

  return (
    <div className="overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <form className="dialog rise" ref={ref} onSubmit={submit} aria-labelledby="auth-h">
        <button type="button" className="dlg-close" onClick={onClose} aria-label="Close">×</button>
        {mode === 'login' ? (
          <>
            <h2 id="auth-h">Welcome back</h2>
            <p className="sub">Use <b>admin@tntech.edu</b> for the admin view.</p>
            {error && <p className="note err">{error}</p>}
            <div className="field"><label htmlFor="lg-email">Email <span className="req">*</span></label><input id="lg-email" className="input" type="email" autoComplete="email" value={form.email} onChange={set('email')} placeholder="name@tntech.edu" /></div>
            <div className="field"><label htmlFor="lg-pass">Password <span className="req">*</span></label><input id="lg-pass" className="input" type="password" autoComplete="current-password" value={form.password} onChange={set('password')} placeholder="••••••••" /></div>
            <div className="field-actions"><button className="btn btn-primary btn-block">Log in</button><button type="button" className="btn-quiet" onClick={onSwitch}>Need an account? Register</button></div>
          </>
        ) : (
          <>
            <h2 id="auth-h">Create your account</h2>
            <p className="sub">New signups are students — admin is added manually.</p>
            {error && <p className="note err">{error}</p>}
            <div className="row2"><div className="field"><label htmlFor="rg-first">First name</label><input id="rg-first" className="input" value={form.firstname} onChange={set('firstname')} /></div><div className="field"><label htmlFor="rg-last">Last name</label><input id="rg-last" className="input" value={form.lastname} onChange={set('lastname')} /></div></div>
            <div className="field"><label htmlFor="rg-phone">Phone</label><input id="rg-phone" className="input" type="tel" value={form.phone} onChange={set('phone')} /></div>
            <div className="field"><label htmlFor="rg-email">Email <span className="req">*</span></label><input id="rg-email" className="input" type="email" value={form.email} onChange={set('email')} /></div>
            <div className="field"><label htmlFor="rg-pass">Password <span className="req">*</span></label><input id="rg-pass" className="input" type="password" value={form.password} onChange={set('password')} /></div>
            <div className="field-actions"><button className="btn btn-primary btn-block">Create account</button><button type="button" className="btn-quiet" onClick={onSwitch}>Back to login</button></div>
          </>
        )}
      </form>
    </div>
  )
}
