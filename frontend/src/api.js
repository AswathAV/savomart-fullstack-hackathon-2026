const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
export const session = { get id() { return localStorage.getItem('uid') }, set id(v) { localStorage.setItem('uid', v) } }

async function req(method, path, body) {
  let r
  try {
    r = await fetch(BASE + '/api' + path, { method, headers: { 'Content-Type': 'application/json', 'X-User-Id': session.id || '' }, body: body ? JSON.stringify(body) : undefined })
  } catch { const e = new Error('Network unreachable'); e.network = true; throw e }
  if (!r.ok) {
    let d; try { d = (await r.json()).detail } catch { /* ignore */ }
    const msg = Array.isArray(d) ? d.map(x => `${(x.loc || []).slice(1).join('.')}: ${x.msg}`).join('; ') : typeof d === 'string' ? d : d?.message || r.statusText
    const e = new Error(msg); e.status = r.status; e.detail = d; throw e
  }
  return r.json()
}
export const api = { get: p => req('GET', p), post: (p, b) => req('POST', p, b || {}), patch: (p, b) => req('PATCH', p, b), put: (p, b) => req('PUT', p, b) }
