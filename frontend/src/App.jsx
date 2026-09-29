import { useEffect, useState } from 'react'
import { api, session } from './api'
import { Activity, Spinner, ErrorBox } from './components.jsx'
import Areas from './pages/Areas.jsx'
import { Pipeline } from './pages/Pipeline.jsx'
import { Scout, AddProperty } from './pages/Field.jsx'
import { Surveys, MyTasks } from './pages/Survey.jsx'

const NAV = {
  bd_manager: [['areas', 'Areas'], ['pipeline', 'Pipeline'], ['surveys', 'Studies'], ['activity', 'Activity']],
  bd_executive: [['scout', 'Scout'], ['add', 'Add property'], ['mine', 'My properties'], ['activity', 'Activity']],
  survey_manager: [['surveys', 'Studies'], ['activity', 'Activity']],
  survey_executive: [['tasks', 'My tasks'], ['activity', 'Activity']],
}
const Seal = () => <svg width="34" height="34" viewBox="0 0 100 100"><polygon fill="#FFF200" points={Array.from({ length: 24 }, (_, i) => { const a = i / 24 * 2 * Math.PI, r = i % 2 ? 40 : 49; return `${50 + r * Math.cos(a)},${50 + r * Math.sin(a)}` }).join(' ')} /><path d="M30 52l14 14 27-30" stroke="#782B90" strokeWidth="11" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>

export default function App() {
  const [users, setUsers] = useState(null), [err, setErr] = useState(null)
  const [uid, setUid] = useState(session.id), [view, setView] = useState({ page: null, params: {} }), [online, setOnline] = useState(navigator.onLine)
  useEffect(() => { api.get('/users').then(u => { setUsers(u); if (!u.find(x => String(x.id) === uid)) pick(String(u[0].id), u) }).catch(setErr) }, [])
  useEffect(() => { const a = () => setOnline(true), b = () => setOnline(false); addEventListener('online', a); addEventListener('offline', b); return () => { removeEventListener('online', a); removeEventListener('offline', b) } }, [])
  const pick = (id, list = users) => { session.id = id; setUid(id); const u = list.find(x => String(x.id) === id); setView({ page: NAV[u.role][0][0], params: {} }) }
  const go = (page, params = {}) => setView({ page, params })
  if (err) return <main><ErrorBox e={new Error('Cannot reach the API at http://localhost:8000. Is the backend running?')} /></main>
  if (!users) return <main><Spinner text="Loading SiteScout" /></main>
  const me = users.find(x => String(x.id) === uid), nav = NAV[me.role], { page, params } = view
  const P = { key: uid + page, go, ...params }
  return <>
    <header className="top"><div className="top-in">
      <div className="brand"><Seal /><div>SiteScout<small>Savomart · Chennai expansion</small></div></div>
      <nav>{nav.map(([k, l]) => <button key={k} className={k === page ? 'on' : ''} onClick={() => go(k)}>{l}</button>)}</nav>
      <div className="who"><select aria-label="Switch demo user" value={uid} onChange={e => pick(e.target.value)}>{users.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}</select></div>
    </div></header>
    {!online && <div className="offline">You are offline. Field captures are saved on this device and sync when you reconnect.</div>}
    <main>
      {page === 'areas' && <Areas {...P} />}
      {page === 'pipeline' && <Pipeline {...P} me={me} />}
      {page === 'mine' && <Pipeline {...P} me={me} />}
      {page === 'surveys' && <Surveys {...P} me={me} />}
      {page === 'activity' && <Activity />}
      {page === 'scout' && <Scout {...P} />}
      {page === 'add' && <AddProperty {...P} />}
      {page === 'tasks' && <MyTasks {...P} />}
    </main>
  </>
}
