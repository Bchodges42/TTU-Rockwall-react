import { useEffect, useState } from 'react'
import MainPage from './components/MainPage.jsx'
import AdminPage from './components/AdminPage.jsx'
import LoginDialog from './components/LoginDialog.jsx'
import BookingDialog from './components/BookingDialog.jsx'
import { loadRockwallData } from './services/rockwallService.js'

const HOURS_LINK = 'https://www.tntech.edu/recreation/hours.php'
const HERO_IMG = '/hero.jpg'

function clock() {
  const d = new Date()
  return `${d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })} · ${d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })}`
}

export default function App() {
  const [role, setRole] = useState(null)
  const [view, setView] = useState(null) // null | 'login' | 'register' | 'dashboard'
  const [tab, setTab] = useState('availability')
  const [page, setPage] = useState('home') // 'home' | 'more' | 'admin'
  const [theme, setTheme] = useState(() => localStorage.getItem('ttu-theme') || 'light')
  const [data, setData] = useState({
    capacity: { active: 4, max: 20 },
    events: [], faqs: [], equipment: [], peak: [], leaderboard: [],
    routes: [], feedback: [],
    siteContent: { hero_title: '', hours_today: '', site_title: '', site_kicker: '' },
    appointments: [],
  })

  const isAdmin = role === 'admin'

  useEffect(() => { document.documentElement.setAttribute('data-theme', theme); localStorage.setItem('ttu-theme', theme) }, [theme])

  async function load() {
    try {
      const fresh = await loadRockwallData(isAdmin)
      setData(current => ({ ...current, ...fresh }))
    } catch { /* backend unavailable */ }
  }
  useEffect(() => {
    load()
    const timer = setInterval(load, 300000)
    return () => clearInterval(timer)
  }, [role]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (role) localStorage.setItem('ttu-role', role); else localStorage.removeItem('ttu-role')
  }, [role])

  const pct = data.capacity.max ? Math.round((data.capacity.active / data.capacity.max) * 100) : 0
  const capCls = data.capacity.active >= data.capacity.max ? 'full' : pct >= 70 ? 'tight' : ''
  const heroChip = isAdmin ? { cls: 'c-accent', label: 'Admin mode' }
    : data.capacity.active >= data.capacity.max ? { cls: 'c-err', label: 'Full' }
    : pct >= 70 ? { cls: 'c-warn', label: 'Busy' } : { cls: 'c-ok', label: 'Open' }

  return (
    <div className="shell">
      <section className="hero" style={{ backgroundImage: `linear-gradient(180deg, rgba(26,19,6,.16) 0%, rgba(26,19,6,.48) 70%, rgba(26,19,6,.64) 100%), url("${HERO_IMG}")` }}>
        <div className="hero-top">
          <div className="hero-brand">
            <div className="hero-logo"><img src="https://www.tntech.edu/digitalswag/images/gifs/Animated_Graphic_T-Eagle_Logo.gif" alt="TTU eagle" /></div>
            <div>
              <h1>{data.siteContent.site_title || 'TTU Rockwall'}</h1>
              <p>{data.siteContent.site_kicker || 'Campus Recreation · Climbing Wall'}</p>
            </div>
          </div>
          <div className="hero-actions">
            <nav className="hero-nav" aria-label="Pages">
              <button className={page==='home' ? 'on' : ''} onClick={() => setPage('home')}>Home</button>
              <button className={page==='more' ? 'on' : ''} onClick={() => setPage('more')}>More</button>
              {isAdmin && <button className={page==='admin' ? 'on' : ''} onClick={() => setPage('admin')}>Admin</button>}
            </nav>
            <button className="icon-btn" onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')} aria-label="Toggle theme">{theme === 'dark' ? '☀︎' : '☾'}</button>
            {role
              ? <button className="hero-cta" onClick={() => { setRole(null); setView(null); setTab('availability'); setPage('home') }}>Sign out</button>
              : <button className="hero-cta" onClick={() => setView('login')}>Log in</button>}
          </div>
        </div>
        <div className="hero-bottom">
          <div className="hero-bottom-left">
            <span className="hero-tag"><i className={heroChip.cls} /> {heroChip.label}</span>
            <h2 className="hero-title">{data.siteContent.hero_title || 'Where campus learns to climb.'}</h2>
            <span className="hero-meta"><b>{data.capacity.active} / {data.capacity.max}</b> climbers · today <b>{data.siteContent.hours_today || '3 PM – 8 PM'}</b></span>
          </div>
          <div className="hero-bottom-right">
            <div className="hero-stat">
              <p className="k">Capacity</p>
              <div className="v">{data.capacity.active} <small>/ {data.capacity.max}</small></div>
              <div className={`hero-stat-track ${capCls}`}><span style={{ width: `${pct}%` }} /></div>
            </div>
            <div className="hero-stat hours-stat">
              <p className="k">Hours today</p>
              <div className="v v-sm">{data.siteContent.hours_today || '3 PM – 8 PM'}</div>
              <a className="hours-link" href={HOURS_LINK} target="_blank" rel="noreferrer">Full hours ↗</a>
            </div>
          </div>
        </div>
      </section>

      <div className="body-wrap">
        <div className="strip">
          <span><b>{clock()}</b> · {pct}% occupied · auto-refresh every 5 min · <b>{data.siteContent.hours_today || '3 PM – 8 PM'}</b></span>
          <a href={HOURS_LINK} target="_blank" rel="noreferrer">Full active hours ↗</a>
        </div>

        {page === 'admin' && isAdmin
          ? <AdminPage data={data} onDataChanged={load} />
          : <MainPage page={page} data={data} isAdmin={isAdmin} setPage={setPage} onBook={(t = 'schedule') => { setView('dashboard'); setTab(t) }} onDataChanged={load} />}
      </div>

      {(view === 'login' || view === 'register') && (
        <LoginDialog
          mode={view}
          onClose={() => setView(null)}
          onSwitch={() => setView(view === 'login' ? 'register' : 'login')}
          onSuccess={newRole => { setRole(newRole); setView(newRole === 'admin' ? null : 'dashboard'); load() }}
        />
      )}
      {view === 'dashboard' && (
        <BookingDialog tab={tab} setTab={setTab} isAdmin={isAdmin} onClose={() => setView(null)} onDataChanged={load} />
      )}
    </div>
  )
}
