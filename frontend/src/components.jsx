import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { api } from './api'

/* ---- Map ---- */
const M = 111320, REF = 13.0
const dlat = s => s / M, dlng = s => s / (M * Math.cos(REF * Math.PI / 180))
export const cellId = (lat, lng, s = 500) => `${s}:${Math.floor(lat / dlat(s))}:${Math.floor(lng / dlng(s))}`
export const cellBounds = id => { const [s, i, j] = id.split(':').map(Number); return [[i * dlat(s), j * dlng(s)], [(i + 1) * dlat(s), (j + 1) * dlng(s)]] }
export const heat = s => `rgba(120,43,144,${(0.1 + s / 100 * 0.62).toFixed(2)})`

const E = []
export function MapView({ center = [13.0, 80.22], zoom = 11, cells = E, markers = E, onCell, onMap, fit = true, height = 420 }) {
  const el = useRef(), map = useRef(), layer = useRef(), cb = useRef({})
  cb.current = { onCell, onMap }
  useEffect(() => {
    map.current = L.map(el.current, { zoomControl: true }).setView(center, zoom)
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OpenStreetMap contributors' }).addTo(map.current)
    layer.current = L.layerGroup().addTo(map.current)
    map.current.on('click', e => cb.current.onMap?.(e.latlng))
    setTimeout(() => map.current?.invalidateSize(), 100)
    return () => map.current.remove()
  }, [])
  useEffect(() => {
    layer.current.clearLayers(); const pts = []
    cells.forEach(c => {
      const b = c.bounds ? (c.bounds.length === 4 ? [[c.bounds[0], c.bounds[1]], [c.bounds[2], c.bounds[3]]] : c.bounds) : cellBounds(c.id)
      const r = L.rectangle(b, { color: c.stroke || '#782B90', weight: c.stroke ? 3 : 1, fillColor: c.fill || '#782B90', fillOpacity: c.op ?? 0.3 }).addTo(layer.current)
      if (c.tip) r.bindTooltip(c.tip)
      r.on('click', e => { if (cb.current.onCell) { L.DomEvent.stopPropagation(e); cb.current.onCell(c) } })
      pts.push(b[0], b[1])
    })
    markers.forEach(m => {
      const mk = L.circleMarker([m.lat, m.lng], { radius: m.r || 8, color: m.stroke || '#4E1A5F', weight: 2, fillColor: m.color || '#FFF200', fillOpacity: 1 }).addTo(layer.current)
      if (m.label) mk.bindTooltip(m.label, { permanent: m.permanent, direction: 'top' })
      if (m.onClick) mk.on('click', e => { L.DomEvent.stopPropagation(e); m.onClick(m) })
      pts.push([m.lat, m.lng])
    })
    if (fit && pts.length) map.current.fitBounds(pts, { padding: [30, 30], maxZoom: 16 })
  }, [cells, markers, fit])
  useEffect(() => { if (!fit) map.current.setView(center, zoom) }, [center[0], center[1]])
  return <div ref={el} className="map" style={{ height }} />
}

/* ---- Small pieces ---- */
export function Seal({ score, size = 64 }) {
  const pts = Array.from({ length: 32 }, (_, i) => { const a = i / 32 * 2 * Math.PI, r = i % 2 ? 40 : 48; return `${50 + r * Math.cos(a)},${50 + r * Math.sin(a)}` }).join(' ')
  return <svg className="seal" width={size} height={size} viewBox="0 0 100 100" role="img" aria-label={`Score ${score}`}><polygon points={pts} fill="#FFF200" stroke="#782B90" strokeWidth="3" /><text x="50" y="60" textAnchor="middle" fontSize="34" fontWeight="800" fill="#4E1A5F">{score ?? '–'}</text></svg>
}
export const Chip = ({ children, kind = '' }) => <span className={`chip ${kind}`}>{children}</span>
export const Bar = ({ v }) => <div className="bar"><i style={{ width: `${Math.max(2, v)}%` }} /></div>
export const Spinner = ({ text }) => <div className="row muted"><span className="spin" />{text}</div>
export const ErrorBox = ({ e, onRetry }) => e ? <div className="err">{e.message || String(e)} {onRetry && <button className="btn sm ghost" onClick={onRetry}>Retry</button>}</div> : null
export const REC = { PROCEED: 'ok', REVIEW: 'warn', REJECT: 'bad' }
export const STAGE = { scouted: 'Scouted', shortlisted: 'Shortlisted', study_requested: 'Study requested', under_review: 'Under review', approved: 'Approved', rejected: 'Rejected' }
export const ago = t => { const m = (Date.now() - new Date(t)) / 60000; return m < 1 ? 'just now' : m < 60 ? `${Math.round(m)} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago` }
export const stamp = t => new Date(t).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })

export function usePoll(fn, deps, keepGoing, ms = 1500) {
  const [data, setData] = useState(null), [err, setErr] = useState(null)
  useEffect(() => {
    let live = true, t
    const tick = async () => {
      try { const d = await fn(); if (!live) return; setData(d); setErr(null); if (keepGoing(d)) t = setTimeout(tick, ms) } catch (e) { if (live) { setErr(e); t = setTimeout(tick, ms * 3) } }
    }
    tick(); return () => { live = false; clearTimeout(t) }
  }, deps)
  return [data, err, setData]
}

export function Activity() {
  const [ev, err] = usePoll(() => api.get('/activity'), [], () => true, 8000)
  return <div className="card"><h1>Activity</h1><p className="sub">Latest changes across the expansion pipeline.</p><ErrorBox e={err} />
    {!ev ? <Spinner text="Loading" /> : ev.length === 0 ? <p className="muted">Nothing yet. Run an area analysis to get started.</p> : <div className="tl">{ev.map(e => <div key={e.id}><b>{e.actor_name}</b> {e.message}<div className="muted small">{ago(e.ts)}</div></div>)}</div>}</div>
}
