import { useEffect, useState } from 'react'
import { api } from '../api'
import { MapView, Seal, Chip, Bar, Spinner, ErrorBox, usePoll, REC, STAGE, ago, stamp } from '../components.jsx'

const ORDER = ['scouted', 'shortlisted', 'study_requested', 'under_review', 'approved', 'rejected']

export function Pipeline({ me, go }) {
  const [list, setList] = useState(null), [err, setErr] = useState(null), [open, setOpen] = useState(null)
  const load = () => api.get('/properties').then(setList).catch(setErr)
  useEffect(() => { load() }, [])
  if (open) return <PropertyView id={open} me={me} go={go} onBack={() => { setOpen(null); load() }} />
  const markers = (list || []).map(p => ({ lat: p.lat, lng: p.lng, label: p.name, color: p.evaluation?.recommendation === 'PROCEED' ? '#1E8E5A' : p.evaluation?.recommendation === 'REJECT' ? '#C62D3A' : '#FFF200', onClick: () => setOpen(p.id) }))
  return <div className="stack"><div><h1>{me.role === 'bd_manager' ? 'Property pipeline' : 'My properties'}</h1><p className="sub">Every property from first sighting to final decision.</p></div><ErrorBox e={err} onRetry={load} />
    {!list ? <Spinner text="Loading properties" /> : list.length === 0 ? <div className="card muted">No properties yet. {me.role === 'bd_executive' ? 'Add one from the field.' : 'Executives will onboard properties from scouted hotspots.'}</div> : <>
      <MapView markers={markers} height={280} />
      <div className="kan">{ORDER.map(s => <div key={s} className="col"><h3>{STAGE[s]} <Chip>{list.filter(p => p.stage === s).length}</Chip></h3>
        {list.filter(p => p.stage === s).map(p => { const ev = p.evaluation || {}; return <div key={p.id} className="item" onClick={() => setOpen(p.id)}>
          <b>{p.name}</b><div className="row">{ev.status === 'done' ? <><Seal score={ev.score} size={40} /><Chip kind={REC[ev.recommendation]}>{ev.recommendation}</Chip></> : <Chip kind="warn">{ev.status === 'failed' ? 'evaluation failed' : 'evaluating…'}</Chip>}</div>
          <span className="muted small">₹{Math.round(p.details.rent).toLocaleString('en-IN')}/mo · {ago(p.updated_at)}</span></div> })}</div>)}</div></>}
  </div>
}

function PropertyView({ id, me, go, onBack }) {
  const [p, err, setP] = usePoll(() => api.get(`/properties/${id}`), [id], d => d.evaluation?.status === 'running')
  const [pend, setPend] = useState(null), [reason, setReason] = useState(''), [e2, setE2] = useState(null), [busy, setBusy] = useState(false)
  if (!p) return <Spinner text="Loading property" />
  const ev = p.evaluation || {}, mgr = me.role === 'bd_manager', d = p.details
  const move = async () => { setBusy(true); setE2(null); try { await api.post(`/properties/${id}/transition`, { to: pend, reason }); setPend(null); setReason(''); setP(await api.get(`/properties/${id}`)) } catch (x) { setE2(x) } finally { setBusy(false) } }
  const act = async fn => { setE2(null); try { await fn(); setP(await api.get(`/properties/${id}`)) } catch (x) { setE2(x) } }
  return <div className="stack">
    <div className="row"><button className="btn sm ghost" onClick={onBack}>Back</button>
      {mgr && <div className="sp row"><button className="btn sm ghost" onClick={() => act(() => api.post(`/properties/${id}/reevaluate`))}>Re-evaluate</button>
        {!p.surveys.length && <button className="btn sm alt" onClick={async () => { try { await api.post('/surveys', { property_id: id }); go('surveys') } catch (x) { setE2(x) } }}>Request catchment study</button>}</div>}</div>
    <ErrorBox e={err || e2} />
    <div className="card row"><Seal score={ev.score} size={96} /><div><h1>{p.name}</h1><div className="row"><Chip kind="y">{STAGE[p.stage]}</Chip>{ev.status === 'done' && <Chip kind={REC[ev.recommendation]}>{ev.recommendation}</Chip>}{p.surveys.map(s => <Chip key={s.id}>Study #{s.id}: {s.status}</Chip>)}</div>
      {ev.status === 'running' && <Spinner text="Evaluating against public data around the pin…" />}{ev.status === 'failed' && <ErrorBox e={new Error(ev.error)} />}</div></div>
    {ev.status === 'done' && <>
      <div className="card"><h2>30-second view</h2><div className="grid2" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))' }}>
        {[['Location', ev.breakdown.location], ['Commercial', ev.breakdown.commercial], ['Physical', ev.breakdown.physical]].map(([l, v]) => <div key={l}><div className="muted small">{l}</div><div className="big">{v}</div><Bar v={v} /></div>)}
        <div><div className="muted small">Rent vs benchmark</div><div className="big">₹{ev.rent_psf}</div><div className="small muted">vs ₹{ev.benchmark_psf}/sqft (mock)</div></div>
        <div><div className="muted small">Nearest Savomart</div><div className="big">{ev.nearest_store_km ?? '–'} km</div></div></div></div>
      <div className="grid2"><div className="card"><h2>Insights</h2><ul className="ins good">{ev.insights.map((x, i) => <li key={i}>{x}</li>)}</ul><h2>Risks</h2><ul className="ins risk">{ev.risks.map((x, i) => <li key={i}>{x}</li>)}</ul>
        <p className="small muted">Evaluated {stamp(ev.data.evaluated_at)} · {ev.data.osm.label}{ev.catchment_used ? ' · includes catchment study data' : ''}</p>{ev.data.osm.source === 'simulated' && <div className="note">Simulated map data used.</div>}</div>
        <div className="stack"><MapView markers={[{ lat: p.lat, lng: p.lng, label: p.name, r: 11 }]} zoom={16} center={[p.lat, p.lng]} fit={false} height={250} />
          {ev.catchment && <div className="card"><h3>Catchment study</h3><ul className="ins">{ev.catchment.insights.map((x, i) => <li key={i}>{x}</li>)}</ul><span className="small muted">Data captured {stamp(ev.catchment.oldest)} to {stamp(ev.catchment.freshest)}</span></div>}</div></div></>}
    <div className="grid2"><div className="card"><h2>Field details</h2><table><tbody>
      {[['Rent', `₹${d.rent.toLocaleString('en-IN')}/month`], ['Area', `${d.area_sqft} sqft`], ['Frontage', d.frontage_ft ? `${d.frontage_ft} ft` : 'not captured'], ['Floor', d.floor === 0 ? 'Ground' : d.floor], ['Parking', d.parking ? 'Yes' : 'No'], ['Road width', d.road_width_ft ? `${d.road_width_ft} ft` : 'not captured'], ['Deposit', d.deposit_months ? `${d.deposit_months} months` : 'not captured'], ['Owner', d.owner_phone || 'not captured'], ['Notes', d.notes || '–']].map(([k, v]) => <tr key={k}><th>{k}</th><td>{v}</td></tr>)}</tbody></table>
      {p.photos.length > 0 && <div className="photos" style={{ marginTop: 10 }}>{p.photos.map((s, i) => <img key={i} src={s} alt={`Site photo ${i + 1}`} />)}</div>}</div>
      <div className="stack">{mgr && p.allowed.length > 0 && <div className="card"><h2>Decide</h2><div className="row">{p.allowed.map(s => <button key={s} className={`btn sm ${s === 'rejected' ? 'bad' : ''}`} onClick={() => setPend(s)}>{s === 'rejected' ? 'Reject' : `Move to ${STAGE[s]}`}</button>)}</div>
        {pend && <div style={{ marginTop: 10 }}><label>Why move to “{STAGE[pend]}”?<textarea rows={2} value={reason} onChange={e => setReason(e.target.value)} placeholder="Reason is saved in the history" /></label><div className="row"><button className="btn" disabled={busy || reason.trim().length < 3} onClick={move}>Confirm</button><button className="btn ghost" onClick={() => setPend(null)}>Cancel</button></div></div>}</div>}
        <div className="card"><h2>History</h2><div className="tl">{p.history.map(h => <div key={h.id}><b>{h.actor_name}</b> {h.message}<div className="muted small">{ago(h.ts)}</div></div>)}</div></div></div></div>
  </div>
}
