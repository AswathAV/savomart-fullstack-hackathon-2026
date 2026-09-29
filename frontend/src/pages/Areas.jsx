import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { MapView, Seal, Chip, Bar, Spinner, ErrorBox, usePoll, heat, cellId, ago, stamp } from '../components.jsx'

export default function Areas({ go }) {
  const [mode, setMode] = useState('search'), [q, setQ] = useState(''), [sel, setSel] = useState({ name: '', cells: [], center: null })
  const [reports, setReports] = useState(null), [open, setOpen] = useState(null), [cmp, setCmp] = useState([]), [err, setErr] = useState(null), [busy, setBusy] = useState(false), [showCmp, setShowCmp] = useState(false)
  const load = () => api.get('/reports').then(setReports).catch(setErr)
  useEffect(() => { load() }, [])
  const find = async () => { setErr(null); try { setSel(await api.post('/resolve', { mode: /^\d+$/.test(q) ? 'pincode' : 'locality', query: q })) } catch (e) { setErr(e) } }
  const toggle = ll => { const id = cellId(ll.lat, ll.lng); setSel(s => ({ name: '', center: s.center, cells: s.cells.includes(id) ? s.cells.filter(c => c !== id) : [...s.cells, id] })) }
  const run = async () => {
    setBusy(true); setErr(null)
    try { const r = await api.post('/reports', { name: sel.name, mode: mode === 'grid' ? 'grid' : /^\d+$/.test(q) ? 'pincode' : 'locality', query: q, cells: sel.cells }); setOpen(r.id); load() } catch (e) { setErr(e) } finally { setBusy(false) }
  }
  const cells = useMemo(() => sel.cells.map(id => ({ id, fill: '#FFF200', stroke: '#782B90', op: .35 })), [sel.cells])
  if (showCmp) return <Compare ids={cmp} onBack={() => setShowCmp(false)} />
  if (open) return <ReportView id={open} onBack={() => { setOpen(null); load() }} go={go} />
  return <div className="split">
    <div className="stack">
      <div className="card">
        <h1>Explore areas</h1><p className="sub">Pick an area, run a virtual analysis, and decide where to scout before anyone leaves the office.</p>
        <div className="row" style={{ marginBottom: 10 }}>
          <button className={`btn sm ${mode === 'search' ? '' : 'ghost'}`} onClick={() => setMode('search')}>Locality / pincode</button>
          <button className={`btn sm ${mode === 'grid' ? '' : 'ghost'}`} onClick={() => { setMode('grid'); setSel({ name: '', cells: [], center: sel.center }) }}>Pick grid cells</button>
        </div>
        {mode === 'search' ? <div className="row"><input style={{ flex: 1 }} placeholder="e.g. Velachery or 600042" value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => e.key === 'Enter' && find()} /><button className="btn" onClick={find}>Find</button></div>
          : <p className="small muted">Tap the map to add or remove 500 m cells. Each cell is about 0.25 km².</p>}
        <ErrorBox e={err} />
        {sel.cells.length > 0 && <div className="note">{sel.name || 'Custom selection'}: <b>{sel.cells.length} cells</b> (~{(sel.cells.length * .25).toFixed(1)} km²)</div>}
        <button className="btn alt" disabled={!sel.cells.length || busy} onClick={run}>Run virtual analysis</button>
      </div>
      <div className="card">
        <div className="row"><h2 style={{ margin: 0 }}>Saved reports</h2><button className="btn sm sp" disabled={cmp.length !== 2} onClick={() => setShowCmp(true)}>Compare ({cmp.length}/2)</button></div>
        {!reports ? <Spinner text="Loading reports" /> : reports.length === 0 ? <p className="muted">No reports yet. Search a locality above to create your first.</p> :
          <div className="stack" style={{ marginTop: 10 }}>{reports.map(r => <div key={r.id} className="item" onClick={() => setOpen(r.id)}>
            <input type="checkbox" style={{ width: 18 }} checked={cmp.includes(r.id)} disabled={r.status !== 'done'} onClick={e => e.stopPropagation()} onChange={e => setCmp(c => e.target.checked ? [...c, r.id].slice(-2) : c.filter(x => x !== r.id))} aria-label="Select to compare" />
            {r.status === 'done' ? <Seal score={Math.round(r.score)} size={46} /> : <Chip kind={r.status === 'failed' ? 'bad' : 'warn'}>{r.status}</Chip>}
            <div><b>{r.name}</b><div className="muted small">{r.rating || r.stage} · {r.cell_count} cells · {ago(r.created_at)}</div></div>
          </div>)}</div>}
      </div>
    </div>
    <MapView cells={cells} onMap={mode === 'grid' ? toggle : undefined} fit={mode === 'search'} height={640} center={sel.center || [13.0, 80.22]} zoom={sel.center ? 14 : 11} />
  </div>
}

function ReportView({ id, onBack, go }) {
  const [r, err, setR] = usePoll(() => api.get(`/reports/${id}`), [id], d => d.status === 'pending' || d.status === 'running')
  const [execs, setExecs] = useState([]), [dir, setDir] = useState(null), [msg, setMsg] = useState(null), [e2, setE2] = useState(null)
  useEffect(() => { api.get('/users').then(u => setExecs(u.filter(x => x.role === 'bd_executive'))) }, [])
  if (!r) return <Spinner text="Loading report" />
  const back = <button className="btn sm ghost" onClick={onBack}>Back to areas</button>
  if (r.status !== 'done') return <div className="card stack">{back}<h1>{r.name}</h1>
    {r.status === 'failed' ? <><ErrorBox e={new Error(`${r.stage}. ${r.error}`)} /><button className="btn" onClick={async () => { setR(await api.post(`/reports/${id}/retry`)) }}>Retry analysis</button></>
      : <><Spinner text={r.stage} /><Bar v={r.progress} /><p className="muted small">Fetching map data can take up to a minute for large areas. You can leave this page; the report saves automatically.</p></>}</div>
  const R = r.result, P = R.provenance, sim = P.osm.source === 'simulated'
  const cells = R.cells.map(c => ({ id: c.id, fill: '#782B90', op: .1 + c.score / 100 * .6, tip: `Cell score ${c.score}` }))
  const markers = [...R.hotspots.map(h => ({ lat: h.lat, lng: h.lng, label: `#${h.rank} scout here (${h.score})`, permanent: true, r: 11, onClick: () => setDir(h) })), ...R.stores.map(s => ({ lat: s.lat, lng: s.lng, label: s.name, color: '#fff', r: 6 }))]
  const send = async e => { e.preventDefault(); const f = new FormData(e.target); setE2(null); try { await api.post('/directives', { report_id: id, label: `${r.name} hotspot #${dir.rank}`, lat: dir.lat, lng: dir.lng, executive_id: +f.get('ex'), note: f.get('note') }); setMsg(`Sent hotspot #${dir.rank} to the executive.`); setDir(null) } catch (x) { setE2(x) } }
  return <div className="stack">
    <div className="row">{back}<button className="btn alt sp" onClick={async () => { try { await api.post('/surveys', { report_id: id }); go('surveys') } catch (x) { setE2(x) } }}>Request catchment study</button></div>
    <ErrorBox e={err || e2} />{msg && <div className="note">{msg}</div>}
    <div className="card row"><Seal score={Math.round(r.score)} size={92} /><div><h1>{r.name}</h1><Chip kind={r.rating === 'Weak' ? 'bad' : r.rating === 'Moderate' ? 'warn' : 'ok'}>{r.rating} fit</Chip> <span className="muted small">{R.area.cells} cells · {R.area.km2} km² · report #{r.id}</span></div></div>
    {sim && <div className="note"><b>Simulated map data.</b> {P.osm.warning} Scores are illustrative only. Re-run when the network is available.</div>}
    <div className="grid2">
      <div className="card"><h2>Why this rating</h2><p>{R.narrative.text}</p><p className="small muted">{R.narrative.source.startsWith('llm') ? <Chip kind="ok">AI-written, numbers verified</Chip> : <Chip>Template summary</Chip>} {R.narrative.note}</p>
        {R.factors.map(f => <div key={f.key} className="factor" title={f.explain}><div><b>{f.label}</b><div className="muted small">weight {Math.round(f.weight * 100)}%</div></div><div><Bar v={f.score} /><div className="small muted">{f.explain}</div></div><b>{f.score}</b></div>)}</div>
      <div className="stack"><MapView cells={cells} markers={markers} height={380} />
        <p className="small muted">Darker cells score higher. Yellow markers are suggested scouting hotspots; white dots are Savomart stores. Tap a hotspot to direct an executive.</p>
        {dir && <form className="card" onSubmit={send}><h3>Send hotspot #{dir.rank} to an executive</h3><p className="small muted">{dir.reason}</p>
          <label>Executive<select name="ex">{execs.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label><label>Note<input name="note" placeholder="What should they look for?" /></label>
          <div className="row"><button className="btn">Send</button><button type="button" className="btn ghost" onClick={() => setDir(null)}>Cancel</button></div></form>}</div>
    </div>
    <div className="grid2">
      <div className="card"><h2>Scout first</h2>{R.hotspots.map(h => <div key={h.rank} className="item" style={{ marginBottom: 8 }} onClick={() => setDir(h)}><Seal score={h.score} size={44} /><div><b>Hotspot {h.rank}</b><div className="small muted">{h.reason}</div></div></div>)}</div>
      <div className="card"><h2>Data used</h2><table><tbody>
        <tr><th>Map features</th><td>{P.osm.label}<br /><span className="muted small">{P.osm.count} features · fetched {stamp(P.osm.fetched_at)}</span></td></tr>
        <tr><th>Savomart stores</th><td>{P.stores.label}<br /><span className="muted small">{P.stores.count} stores · fetched {stamp(P.stores.fetched_at)}</span></td></tr>
        <tr><th>Demographics</th><td>{P.demographics.label}</td></tr>
        <tr><th>Scoring</th><td>{P.scoring_version}, generated {stamp(P.generated_at)}</td></tr></tbody></table>
        <p className="small muted">Counts in area: {Object.entries(R.metrics).map(([k, v]) => `${k} ${v}`).join(' · ')}</p></div>
    </div>
  </div>
}

function Compare({ ids, onBack }) {
  const [rs, setRs] = useState(null)
  useEffect(() => { Promise.all(ids.map(i => api.get(`/reports/${i}`))).then(setRs) }, [])
  if (!rs) return <Spinner text="Loading comparison" />
  const [a, b] = rs, win = (x, y) => x > y ? 'ok' : x < y ? 'bad' : ''
  return <div className="card stack"><button className="btn sm ghost" onClick={onBack}>Back</button><h1>{a.name} vs {b.name}</h1>
    <table><thead><tr><th>Signal</th><th>{a.name}</th><th>{b.name}</th></tr></thead><tbody>
      <tr><td><b>Overall fit</b></td><td><Chip kind={win(a.score, b.score)}>{a.score}</Chip></td><td><Chip kind={win(b.score, a.score)}>{b.score}</Chip></td></tr>
      {a.result.factors.map((f, i) => { const g = b.result.factors[i]; return <tr key={f.key}><td>{f.label}<div className="muted small">weight {Math.round(f.weight * 100)}%</div></td><td><Chip kind={win(f.score, g.score)}>{f.score}</Chip><div className="small muted">{f.explain}</div></td><td><Chip kind={win(g.score, f.score)}>{g.score}</Chip><div className="small muted">{g.explain}</div></td></tr> })}
      <tr><td>Analysed</td><td>{stamp(a.finished_at)}</td><td>{stamp(b.finished_at)}</td></tr></tbody></table></div>
}
