import { useEffect, useState } from 'react'
import MainPage from './components/MainPage.jsx'
import AdminPage from './components/AdminPage.jsx'
import LoginDialog from './components/LoginDialog.jsx'
import BookingDialog from './components/BookingDialog.jsx'
import ManageBooking from './components/ManageBooking.jsx'
import StaffQueue from './components/StaffQueue.jsx'
import { authService, loadRockwallData } from './services/rockwallService.js'
import { fmtTime, relDay } from './services/format.js'

const HOURS_LINK = 'https://www.tntech.edu/recreation/hours.php'
const HERO_IMG = '/hero.jpg'

// The single place the site says whether the wall is open, driven by the real weekly hours.
function statusLine(hours, capacity) {
  const now = hours?.now
  if (!now) return null
  if (now.open) return { open: true, label: 'Open now', rest: `${capacity.active} of ${capacity.max} climbing · closes ${fmtTime(now.closes)}` }
  if (now.next) return { open: false, label: 'Closed', rest: `opens ${relDay(now.next.date)} at ${fmtTime(now.next.opens)}` }
  return { open: false, label: 'Closed', rest: 'see campus hours for reopening' }
}

export default function App() {
  const [user, setUser] = useState(null)
  const [loadError, setLoadError] = useState('')
  const [view, setView] = useState(null) // null | 'login' | 'register' | 'bookings'
  const [page, setPage] = useState(() => window.location.pathname === '/booking' ? 'manage' : 'home') // home | more | admin | manage
  const [theme, setTheme] = useState(() => localStorage.getItem('ttu-theme') || 'light')
  const [data, setData] = useState({
    capacity: { active: 0, max: 20 }, hours: null,
    events: [], faqs: [], equipment: [], peak: [], leaderboard: [],
    routes: [], feedback: [],
    siteContent: { hero_title: '', site_title: '', site_kicker: '' },
    appointments: [],
  })

  const role = user?.role
  const isAdmin = role === 'admin'
  const isStaff = isAdmin || role === 'moderator'

  async function refreshUser() {
    try { setUser(await authService.me()) } catch { setUser(null) }
  }
  useEffect(() => { refreshUser() }, [])

  useEffect(() => { document.documentElement.setAttribute('data-theme', theme); localStorage.setItem('ttu-theme', theme) }, [theme])

  async function load() {
    try {
      const fresh = await loadRockwallData(isAdmin)
      setData(current => ({ ...current, ...fresh }))
      setLoadError('')
    } catch (error) { setLoadError(error.message) }
  }
  useEffect(() => {
    load()
    const timer = setInterval(load, 60000)
    return () => clearInterval(timer)
  }, [role]) // eslint-disable-line react-hooks/exhaustive-deps

  async function signOut() {
    try {
      await authService.logout()
      setUser(null); setView(null); setPage('home')
      setData(current => ({ ...current, appointments: [] }))
    } catch (error) { setLoadError(error.message) }
  }

  function goHome() {
    if (window.location.pathname !== '/') window.history.replaceState(null, '', '/')
    setPage('home')
  }
  function goBook() {
    goHome()
    requestAnimationFrame(() => document.getElementById('book')?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
  }

  const status = statusLine(data.hours, data.capacity)

  return (
    <div className="shell">
      <section className="hero" style={{ backgroundImage: `linear-gradient(180deg, rgba(26,19,6,.10) 0%, rgba(26,19,6,.38) 62%, rgba(26,19,6,.66) 100%), url("${HERO_IMG}")` }}>
        <div className="hero-top">
          <button type="button" className="hero-brand" onClick={goHome}>
            <div className="hero-logo"><img src="https://www.tntech.edu/digitalswag/images/gifs/Animated_Graphic_T-Eagle_Logo.gif" alt="" /></div>
            <div>
              <h1>{data.siteContent.site_title || 'TTU Rockwall'}</h1>
              <p>{data.siteContent.site_kicker || 'Campus Recreation · Climbing Wall'}</p>
            </div>
          </button>
          <div className="hero-actions">
            <nav className="hero-nav" aria-label="Pages">
              <button className={page === 'home' ? 'on' : ''} onClick={goHome}>Home</button>
              <button className={page === 'more' ? 'on' : ''} onClick={() => setPage('more')}>Gear &amp; FAQ</button>
              {user && <button onClick={() => setView('bookings')}>My bookings</button>}
              {isStaff && <button className={page === 'admin' ? 'on' : ''} onClick={() => setPage('admin')}>{isAdmin ? 'Admin' : 'Staff'}</button>}
            </nav>
            <button className="icon-btn" onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')} aria-label="Toggle theme">{theme === 'dark' ? '☀︎' : '☾'}</button>
            {user
              ? <button className="hero-cta ghost" onClick={signOut}>Sign out</button>
              : <button className="hero-cta ghost" onClick={() => setView('login')}>Log in</button>}
          </div>
        </div>
        <div className="hero-bottom">
          <div className="hero-bottom-left">
            <h2 className="hero-title">{data.siteContent.hero_title || 'Where campus learns to climb.'}</h2>
            {status && (
              <p className="hero-status">
                <b className={status.open ? 'is-open' : 'is-closed'}>{status.label}</b> · {status.rest}
                {' · '}<a href={HOURS_LINK} target="_blank" rel="noreferrer">Campus hours ↗</a>
              </p>
            )}
          </div>
          {page !== 'admin' && <button className="hero-cta" onClick={goBook}>Book a time</button>}
        </div>
      </section>

      <div className="body-wrap">
        {loadError && <p className="note err" role="alert">Live data could not be refreshed: {loadError}</p>}
        {page === 'manage'
          ? <ManageBooking token={new URLSearchParams(window.location.hash.slice(1) || window.location.search).get('token')} onHome={goBook} />
          : page === 'admin' && isStaff
            ? <><StaffQueue onDataChanged={load} />{isAdmin && <AdminPage data={data} onDataChanged={load} />}</>
            : <MainPage page={page} data={data} user={user} onFind={() => setView(user ? 'bookings' : 'find')} onDataChanged={load} />}
      </div>

      {(view === 'login' || view === 'register') && (
        <LoginDialog
          mode={view}
          onClose={() => setView(null)}
          onSwitch={() => setView(view === 'login' ? 'register' : 'login')}
          onSuccess={() => { setView(null); refreshUser() }}
        />
      )}
      {(view === 'bookings' || view === 'find') && (
        <BookingDialog user={view === 'bookings' ? user : null} onClose={() => setView(null)} onDataChanged={load} />
      )}
    </div>
  )
}
