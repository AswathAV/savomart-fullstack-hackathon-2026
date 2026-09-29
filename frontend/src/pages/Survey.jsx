import { useEffect, useState } from 'react'
import { api } from '../api'
import { MapView, Chip, Bar, Spinner, ErrorBox, usePoll, ago, stamp } from '../components.jsx'

export function Surveys({ me, go, open: initial }) {
  const [list, setList] = useState(null), [err, setErr] = useState(null), [open, setOpen] = useState(initial || null)
  const load = () => api.get('/surveys').then(setList).catch(setErr)
  useEffect(() => { load() }, [])
  if (open) return <SurveyView id={open} me={me} onBack={() => { setOpen(null); load() }} />
  return <div className="stack"><div><h1>Catchment studies</h1><p className="sub">{me.role === 'survey_manager' ? 'Incoming requests. Split each into cell tasks and assign your team.' : 'Requested studies and their progress.'}</p></div><ErrorBox e={err} onRetry={load} />
    {!list ? <Spinner text="Loading studies" /> : list.length === 0 ? <div className="card muted">No studies requested yet. Request one from a property or an analysed area.</div> :
      list.map(s => <div key={s.id} className="item" onClick={() => setOpen(s.id)}><div style={{ flex: 1 }}><b>{s.title}</b><div className="muted small">{ago(s.created_at)} · {s.plan} cells</div>{s.progress.total > 0 && <Bar v={s.progress.done / s.progress.total * 100} />}</div>
        <Chip kind={s.status === 'complete' ? 'ok' : s.status === 'requested' ? 'warn' : ''}>{s.status.replace('_', ' ')}</Chip>{s.progress.total > 0 && <span className="small muted">{s.progress.done}/{s.progress.total}</span>}</div>)}</div>
}

function SurveyView({ id, me, onBack }) {
  const [s, err, setS] = usePoll(() => api.get(`/surveys/${id}`), [id], d => d.status !== 'complete', 5000)
  const [execs, setExecs] = useState([]), [pick, setPick] = useState([]), [e2, setE2] = useState(null)
  useEffect(() => { api.get('/users').then(u => { const x = u.filter(y => y.role === 'survey_executive'); setExecs(x); setPick(x.map(y => y.id)) }) }, [])
  if (!s) return <Spinner text="Loading study" />
  const sm = me.role === 'survey_manager', name = i => execs.find(e => e.id === i)?.name.split(' ')[0] || 'Unassigned'
  const act = async fn => { setE2(null); try { setS(await fn()) } catch (x) { setE2(x) } }
  const col = { open: '#FFF200', in_progress: '#F4A300', done: '#1E8E5A', reused: '#782B90' }
  const cells = s.tasks.length ? s.tasks.map(t => ({ id: t.cell_id, bounds: t.bounds, fill: col[t.status], op: .55, tip: `${name(t.assignee_id)} · ${t.status}` })) : s.plan_cells.map(c => ({ id: c.id, bounds: c.bounds, fill: '#782B90', op: .2 }))
  return <div className="stack"><button className="btn sm ghost" style={{ width: 'fit-content' }} onClick={onBack}>Back</button><ErrorBox e={err || e2} />
    <div className="card"><div className="row"><h1 style={{ margin: 0 }}>{s.title}</h1><Chip kind={s.status === 'complete' ? 'ok' : 'warn'}>{s.status.replace('_', ' ')}</Chip></div>
      {s.progress.total > 0 && <div style={{ margin: '10px 0' }}><Bar v={s.progress.done / s.progress.total * 100} /><span className="small muted">{s.progress.done} of {s.progress.total} cells complete · {s.progress.reused} reused from fresh studies · {s.progress.assigned} assigned</span></div>}
      {sm && s.status === 'requested' && <div><p className="small muted">{s.plan.length} non-overlapping 250 m cells. Cells already surveyed in the last 90 days are reused instead of re-surveyed.</p><button className="btn alt" onClick={() => act(() => api.post(`/surveys/${id}/split`))}>Split into cell tasks</button></div>}
      {sm && s.status === 'in_progress' && s.tasks.some(t => t.status === 'open') && <div className="row"><span className="small">Auto-assign open cells (compact patches) to:</span>
        {execs.map(e => <label key={e.id} className="row" style={{ margin: 0 }}><input type="checkbox" style={{ width: 18 }} checked={pick.includes(e.id)} onChange={x => setPick(p => x.target.checked ? [...p, e.id] : p.filter(i => i !== e.id))} />{e.name.split(' ')[0]}</label>)}
        <button className="btn sm" disabled={!pick.length} onClick={() => act(() => api.post(`/surveys/${id}/assign`, { executive_ids: pick }))}>Assign</button></div>}</div>
    <div className="grid2"><MapView cells={cells} height={380} markers={s.property ? [{ ...s.property, label: s.property.name, r: 10 }] : []} />
      <div className="card" style={{ maxHeight: 380, overflow: 'auto' }}><h2>Tasks</h2>{s.tasks.length === 0 ? <p className="muted">Not split yet.</p> : <table><tbody>{s.tasks.map(t => <tr key={t.id}><td>{t.cell_id.split(':').slice(1).join('/')}</td><td><Chip kind={t.status === 'done' ? 'ok' : t.status === 'reused' ? 'y' : ''}>{t.status.replace('_', ' ')}</Chip></td>
        <td>{sm && !['done', 'reused'].includes(t.status) ? <select value={t.assignee_id || ''} onChange={e => act(async () => { await api.patch(`/tasks/${t.id}/assign`, { assignee_id: +e.target.value }); return api.get(`/surveys/${id}`) })}><option value="">Unassigned</option>{execs.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}</select> : name(t.assignee_id)}</td></tr>)}</tbody></table>}</div></div>
    {s.rollup && <div className="card"><h2>Catchment insights</h2><div className="row"><div className="big">{s.rollup.score}</div><ul className="ins" style={{ margin: 0 }}>{s.rollup.insights.map((x, i) => <li key={i}>{x}</li>)}</ul></div><p className="small muted">These results are linked to the {s.property ? 'property evaluation' : 'area'} and re-scored automatically.</p></div>}
  </div>
}

/* ---------- Survey executive ---------- */
const QK = 'sitescout-queue'
const queue = () => JSON.parse(localStorage.getItem(QK) || '{}')
async function syncQueue() {
  const q = queue(); let n = 0
  for (const [id, body] of Object.entries(q)) { try { await api.put(`/tasks/${id}`, body); delete q[id]; n++ } catch (e) { if (e.network) break; if (e.status && e.status < 500) delete q[id] } }
  localStorage.setItem(QK, JSON.stringify(q)); return n
}

export function MyTasks() {
  const [ts, setTs] = useState(null), [err, setErr] = useState(null), [open, setOpen] = useState(null), [pending, setPending] = useState(Object.keys(queue()).length)
  const load = () => syncQueue().then(() => { setPending(Object.keys(queue()).length); return api.get('/tasks') }).then(setTs).catch(setErr)
  useEffect(() => { load(); addEventListener('online', load); return () => removeEventListener('online', load) }, [])
  if (open) return <Capture task={open} onBack={() => { setOpen(null); load() }} />
  return <div className="stack"><div><h1>My survey tasks</h1><p className="sub">Walk each cell, note every lane. Drafts save on your phone even without network.</p></div><ErrorBox e={err} onRetry={load} />
    {pending > 0 && <div className="note">{pending} submission(s) waiting for network. They will sync automatically.</div>}
    {!ts ? <Spinner text="Loading tasks" /> : ts.length === 0 ? <div className="card muted">Nothing assigned yet. Your survey manager will assign cells soon.</div> :
      ts.map(t => <div key={t.id} className="item" onClick={() => setOpen(t)}><div style={{ flex: 1 }}><b>{t.place} · cell {t.cell_id.split(':').slice(1).join('/')}</b><div className="muted small">{t.survey_title}</div></div><Chip kind={t.status === 'done' ? 'ok' : t.status === 'in_progress' ? 'warn' : ''}>{t.status === 'open' ? 'to do' : t.status.replace('_', ' ')}</Chip></div>)}</div>
}

const blank = { name: '', lane_width_ft: '', footfall_10min: '', households_est: '', shops: '', competitors: '', income: 'mid', notes: '' }
function Capture({ task, onBack }) {
  const key = `draft:${task.id}`
  const [lanes, setLanes] = useState(() => JSON.parse(localStorage.getItem(key) || 'null') || task.data.lanes || []), [f, setF] = useState(blank), [err, setErr] = useState(null), [msg, setMsg] = useState(null)
  useEffect(() => { localStorage.setItem(key, JSON.stringify(lanes)) }, [lanes])
  const set = k => e => setF({ ...f, [k]: e.target.value })
  const add = () => { if (!f.name.trim() || f.footfall_10min === '') return setErr(new Error('Lane name and footfall count are required')); setErr(null); const n = v => v === '' ? 0 : +v; setLanes([...lanes, { ...f, lane_width_ft: f.lane_width_ft === '' ? null : +f.lane_width_ft, footfall_10min: n(f.footfall_10min), households_est: n(f.households_est), shops: n(f.shops), competitors: n(f.competitors) }]); setF(blank) }
  const send = async submit => {
    const body = { lanes, submit }; setErr(null)
    try { await api.put(`/tasks/${task.id}`, body); if (submit) { localStorage.removeItem(key); onBack() } else setMsg('Draft saved to the server') }
    catch (e) { if (e.network && submit) { const q = queue(); q[task.id] = body; localStorage.setItem(QK, JSON.stringify(q)); localStorage.removeItem(key); setMsg('No network. Saved on this device and will sync when you are back online.'); setTimeout(onBack, 1500) } else if (e.network) setMsg('Offline: draft kept on this device') ; else setErr(e) }
  }
  const done = task.status === 'done'
  return <div className="stack" style={{ maxWidth: 720, margin: 'auto' }}><button className="btn sm ghost" style={{ width: 'fit-content' }} onClick={onBack}>Back</button>
    <div><h1>{task.place} · cell {task.cell_id.split(':').slice(1).join('/')}</h1><p className="sub">{task.survey_title}. Cover only lanes inside the highlighted square.</p></div>
    <MapView cells={[{ id: task.cell_id, bounds: task.bounds, fill: '#FFF200', stroke: '#782B90', op: .25 }]} height={200} />
    <ErrorBox e={err} />{msg && <div className="note">{msg}</div>}
    {!done && <div className="card"><h2>Add a lane</h2><label>Lane / street name<input value={f.name} onChange={set('name')} /></label>
      <div className="grid2"><label>People passing in 10 min<input type="number" inputMode="numeric" value={f.footfall_10min} onChange={set('footfall_10min')} /></label><label>Households (est.)<input type="number" inputMode="numeric" value={f.households_est} onChange={set('households_est')} /></label>
        <label>Shops<input type="number" inputMode="numeric" value={f.shops} onChange={set('shops')} /></label><label>Competing grocers<input type="number" inputMode="numeric" value={f.competitors} onChange={set('competitors')} /></label>
        <label>Lane width (ft)<input type="number" inputMode="numeric" value={f.lane_width_ft} onChange={set('lane_width_ft')} /></label><label>Resident income<select value={f.income} onChange={set('income')}><option value="low">Low</option><option value="mid">Middle</option><option value="high">High</option></select></label></div>
      <label>Notes<input value={f.notes} onChange={set('notes')} /></label><button className="btn" onClick={add}>Add lane</button></div>}
    <div className="card"><h2>Lanes captured ({lanes.length})</h2>{lanes.length === 0 ? <p className="muted">None yet.</p> : lanes.map((l, i) => <div key={i} className="item" style={{ marginBottom: 6, cursor: 'default' }}><div style={{ flex: 1 }}><b>{l.name}</b><div className="small muted">{l.footfall_10min} people/10 min · {l.households_est} households · {l.competitors} competitors · {l.income} income</div></div>{!done && <button className="btn sm ghost" onClick={() => setLanes(lanes.filter((_, j) => j !== i))}>Remove</button>}</div>)}</div>
    {!done && <div className="row"><button className="btn ghost" onClick={() => send(false)}>Save draft</button><button className="btn alt sp" disabled={!lanes.length} onClick={() => send(true)}>Submit cell</button></div>}
  </div>
}
