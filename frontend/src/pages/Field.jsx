import { useEffect, useState } from 'react'
import { api } from '../api'
import { MapView, Chip, Spinner, ErrorBox, ago } from '../components.jsx'

export function Scout({ go }) {
  const [ds, setDs] = useState(null), [err, setErr] = useState(null)
  useEffect(() => { api.get('/directives').then(setDs).catch(setErr) }, [])
  const markers = (ds || []).map(x => ({ lat: x.lat, lng: x.lng, label: x.label, permanent: true, r: 11, color: x.status === 'done' ? '#1E8E5A' : '#FFF200' }))
  return <div className="stack"><div><h1>Where to scout</h1><p className="sub">Hotspots your manager picked from the data. Go there, find a vacant unit, and onboard it.</p></div><ErrorBox e={err} />
    {!ds ? <Spinner text="Loading" /> : ds.length === 0 ? <div className="card muted">No scouting requests yet. You can still add a property you spot.<div><button className="btn" style={{ marginTop: 10 }} onClick={() => go('add')}>Add property</button></div></div> : <div className="split">
      <div className="stack">{ds.map(x => <div key={x.id} className="card"><div className="row"><b>{x.label}</b><Chip kind={x.status === 'done' ? 'ok' : 'warn'}>{x.status === 'done' ? 'Property added' : 'To scout'}</Chip></div>
        <p className="small muted">{x.note || 'No note'} · {ago(x.created_at)}</p><div className="row"><button className="btn sm" onClick={() => go('add', { lat: x.lat, lng: x.lng, directive: x.id })}>Add property here</button>
          <a className="btn sm ghost" style={{ textDecoration: 'none' }} target="_blank" rel="noreferrer" href={`https://www.google.com/maps/dir/?api=1&destination=${x.lat},${x.lng}`}>Navigate</a></div></div>)}</div>
      <MapView markers={markers} height={480} /></div>}</div>
}

const resize = file => new Promise(res => {
  const img = new Image(), fr = new FileReader()
  fr.onload = () => { img.onload = () => { const k = Math.min(1, 900 / Math.max(img.width, img.height)), c = document.createElement('canvas'); c.width = img.width * k; c.height = img.height * k; c.getContext('2d').drawImage(img, 0, 0, c.width, c.height); res(c.toDataURL('image/jpeg', .7)) }; img.src = fr.result }
  fr.readAsDataURL(file)
})

export function AddProperty({ go, lat, lng, directive }) {
  const [pin, setPin] = useState(lat ? { lat, lng } : null), [f, setF] = useState({ name: '', rent: '', area_sqft: '', frontage_ft: '', floor: 0, parking: false, road_width_ft: '', deposit_months: '', owner_phone: '', notes: '' })
  const [photos, setPhotos] = useState([]), [err, setErr] = useState(null), [dup, setDup] = useState(null), [busy, setBusy] = useState(false), [gps, setGps] = useState('')
  const set = k => e => setF({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const locate = () => { setGps('Finding you…'); navigator.geolocation?.getCurrentPosition(p => { setPin({ lat: p.coords.latitude, lng: p.coords.longitude }); setGps(`Accuracy about ${Math.round(p.coords.accuracy)} m`) }, () => setGps('Could not get location. Tap the map to drop the pin.'), { enableHighAccuracy: true, timeout: 15000 }) }
  const num = v => v === '' ? null : Number(v)
  const submit = async force => {
    setErr(null); setDup(null)
    if (!pin) return setErr(new Error('Drop a pin on the map or use your location'))
    if (!f.rent) return setErr(new Error('Monthly rent is required'))
    setBusy(true)
    try { const p = await api.post('/properties', { name: f.name, ...pin, rent: +f.rent, area_sqft: +f.area_sqft, frontage_ft: num(f.frontage_ft), floor: +f.floor, parking: f.parking, road_width_ft: num(f.road_width_ft), deposit_months: num(f.deposit_months), owner_phone: f.owner_phone || null, notes: f.notes, photos, directive_id: directive || null, force: !!force }); go('mine', {}) ; return p }
    catch (e) { e.status === 409 ? setDup(e.detail) : setErr(e) } finally { setBusy(false) }
  }
  return <div className="stack" style={{ maxWidth: 720, margin: 'auto' }}><div><h1>Add a property</h1><p className="sub">Capture what you see. We evaluate it against public data as soon as you save.</p></div>
    <div className="card"><h2>1. Location</h2><div className="row" style={{ marginBottom: 10 }}><button className="btn sm" onClick={locate}>Use my location</button><span className="small muted">{gps || 'or tap the map to move the pin'}</span></div>
      <MapView center={pin ? [pin.lat, pin.lng] : [13.0, 80.22]} zoom={pin ? 17 : 11} fit={false} height={260} onMap={ll => setPin({ lat: ll.lat, lng: ll.lng })} markers={pin ? [{ ...pin, r: 11, label: 'Property' }] : []} /></div>
    <div className="card"><h2>2. Details</h2>
      <label>Name or landmark<input value={f.name} onChange={set('name')} placeholder="e.g. Corner unit opp. Bus stand" /></label>
      <div className="grid2"><label>Monthly rent (₹)<input type="number" inputMode="numeric" value={f.rent} onChange={set('rent')} /></label><label>Area (sqft)<input type="number" inputMode="numeric" value={f.area_sqft} onChange={set('area_sqft')} /></label>
        <label>Frontage (ft)<input type="number" inputMode="numeric" value={f.frontage_ft} onChange={set('frontage_ft')} /></label><label>Road width (ft)<input type="number" inputMode="numeric" value={f.road_width_ft} onChange={set('road_width_ft')} /></label>
        <label>Floor (0 = ground)<input type="number" inputMode="numeric" value={f.floor} onChange={set('floor')} /></label><label>Deposit (months)<input type="number" inputMode="decimal" value={f.deposit_months} onChange={set('deposit_months')} /></label></div>
      <label className="row"><input type="checkbox" style={{ width: 20 }} checked={f.parking} onChange={set('parking')} />Parking available</label>
      <label>Owner phone<input type="tel" value={f.owner_phone} onChange={set('owner_phone')} /></label><label>Notes<textarea rows={2} value={f.notes} onChange={set('notes')} /></label></div>
    <div className="card"><h2>3. Photos</h2><input type="file" accept="image/*" capture="environment" multiple onChange={async e => setPhotos([...photos, ...await Promise.all([...e.target.files].map(resize))].slice(0, 5))} />
      <div className="photos" style={{ marginTop: 8 }}>{photos.map((s, i) => <img key={i} src={s} alt="" onClick={() => setPhotos(photos.filter((_, j) => j !== i))} title="Tap to remove" />)}</div></div>
    <ErrorBox e={err} />
    {dup && <div className="err">{dup.message}. <div className="row" style={{ marginTop: 8 }}><button className="btn sm" onClick={() => submit(true)}>Add anyway</button><button className="btn sm ghost" onClick={() => setDup(null)}>Cancel</button></div></div>}
    <button className="btn alt" style={{ padding: 14 }} disabled={busy} onClick={() => submit(false)}>{busy ? 'Saving…' : 'Save and evaluate'}</button></div>
}
