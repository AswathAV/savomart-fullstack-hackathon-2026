"""Data ingestion: OpenStreetMap (Overpass) + Savomart stores API. Every call returns provenance metadata.
If a source is unreachable we fall back to clearly-flagged simulated data so the workflow never dead-ends."""
import os, json, time, hashlib, random, math
from pathlib import Path
import httpx
from . import geo

OFFLINE = os.getenv("OFFLINE_MODE", "0") == "1"
CACHE = Path(os.getenv("CACHE_DIR", ".cache")); CACHE.mkdir(exist_ok=True)
OVERPASS_URL = os.getenv("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
STORES_URL = os.getenv("SAVO_STORES_URL", "https://internal-service.savomart.in/bridge/api/store/list?is_operational=True")
STORES_TOKEN = os.getenv("SAVO_STORES_TOKEN", "")
CATS = ["competitor", "education", "health", "office", "transit", "housing", "food"]

QL = """[out:json][timeout:60];(
nwr["shop"~"^(supermarket|convenience|grocery|greengrocer|general|department_store)$"]({b});
nwr["amenity"~"^(school|college|university|hospital|clinic|pharmacy|marketplace|restaurant|cafe|fast_food)$"]({b});
nwr["office"]({b});
node["highway"="bus_stop"]({b});
nwr["railway"~"^(station|halt|subway_entrance)$"]({b});
way["building"~"^(apartments|residential|dormitory)$"]({b}););
out center tags 9000;"""


def categorize(t):
    if t.get("shop") in ("supermarket", "convenience", "grocery", "greengrocer", "general", "department_store") or t.get("amenity") == "marketplace":
        return "competitor"
    a = t.get("amenity")
    if a in ("school", "college", "university"): return "education"
    if a in ("hospital", "clinic", "pharmacy"): return "health"
    if a in ("restaurant", "cafe", "fast_food"): return "food"
    if "office" in t: return "office"
    if t.get("highway") == "bus_stop" or "railway" in t: return "transit"
    if t.get("building"): return "housing"


def _overpass(bbox):
    b = ",".join(f"{x:.5f}" for x in bbox)
    last = None
    for attempt in range(3):
        try:
            r = httpx.post(OVERPASS_URL, data={"data": QL.format(b=b)}, timeout=70, headers={"User-Agent": "savo-sitescout/1.0"})
            r.raise_for_status()
            feats = []
            for el in r.json().get("elements", []):
                lat = el.get("lat") or (el.get("center") or {}).get("lat")
                lng = el.get("lon") or (el.get("center") or {}).get("lon")
                cat = categorize(el.get("tags", {}))
                if lat and lng and cat:
                    feats.append({"lat": lat, "lng": lng, "cat": cat, "name": el["tags"].get("name")})
            return {"features": feats, "meta": {"source": "osm-overpass", "label": "OpenStreetMap via Overpass API", "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "count": len(feats)}}
        except Exception as e:  # retry with backoff
            last = e; time.sleep(2 * (attempt + 1))
    raise last


def _simulate(bbox, why="offline mode"):
    """Deterministic pseudo-data scaled by local density. ALWAYS labelled 'simulated' in UI + reports."""
    rng = random.Random(hashlib.md5(json.dumps([round(x, 3) for x in bbox]).encode()).hexdigest())
    lat, lng = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    p = geo.nearest_place(lat, lng)
    km2 = geo.haversine_m(bbox[0], bbox[1], bbox[2], bbox[1]) * geo.haversine_m(bbox[0], bbox[1], bbox[0], bbox[3]) / 1e6
    per_km2 = {"housing": p["pop_km2"] / 150, "competitor": p["pop_km2"] / 4000, "education": p["pop_km2"] / 2500, "health": p["pop_km2"] / 3000,
               "office": p["pop_km2"] / 3000, "transit": p["pop_km2"] / 2500, "food": p["pop_km2"] / 1500}
    feats = []
    for cat, rate in per_km2.items():
        for _ in range(int(rate * km2 * rng.uniform(.7, 1.3))):
            feats.append({"lat": rng.uniform(bbox[0], bbox[2]), "lng": rng.uniform(bbox[1], bbox[3]), "cat": cat, "name": None})
    return {"features": feats, "meta": {"source": "simulated", "label": "SIMULATED data (not real OSM)", "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "count": len(feats), "warning": f"Live OSM unavailable ({why}); values are synthetic."}}


def fetch_features(bbox):
    key = hashlib.md5(json.dumps([round(x, 3) for x in bbox]).encode()).hexdigest()
    f = CACHE / f"osm_{key}.json"
    if f.exists() and time.time() - f.stat().st_mtime < 7 * 86400:
        return json.loads(f.read_text())
    if OFFLINE:
        return _simulate(bbox)
    try:
        res = _overpass(bbox)
        f.write_text(json.dumps(res))
        return res
    except Exception as e:
        return _simulate(bbox, type(e).__name__)


SAMPLE_STORES = [("Savomart Velachery (sample)", 12.9791, 80.2210), ("Savomart Adyar (sample)", 13.0067, 80.2570), ("Savomart Anna Nagar (sample)", 13.0879, 80.2170),
                 ("Savomart Porur (sample)", 13.0358, 80.1590), ("Savomart Chromepet (sample)", 12.9530, 80.1400), ("Savomart Perungudi (sample)", 12.9620, 80.2420)]


def _pick(d, *keys):
    for k in keys:
        if d.get(k) not in (None, ""): return d[k]


def parse_stores(payload):
    items = payload if isinstance(payload, list) else next((v for k, v in payload.items() if isinstance(v, list)), []) if isinstance(payload, dict) else []
    out = []
    for it in items:
        try:
            lat = float(_pick(it, "latitude", "lat")); lng = float(_pick(it, "longitude", "lng", "lon", "long"))
            out.append({"name": str(_pick(it, "name", "store_name", "storeName") or "Savomart"), "lat": lat, "lng": lng})
        except (TypeError, ValueError, AttributeError):
            continue
    return out


def fetch_stores():
    f = CACHE / "stores.json"
    if f.exists() and time.time() - f.stat().st_mtime < 3600:
        return json.loads(f.read_text())
    res = None
    if not OFFLINE and STORES_TOKEN:
        try:  # mirrors the curl in the brief (--data '' => POST with empty body)
            r = httpx.post(STORES_URL, headers={"X-cron-token": STORES_TOKEN}, content=b"", timeout=20)
            r.raise_for_status()
            stores = parse_stores(r.json())
            if stores:
                res = {"stores": stores, "meta": {"source": "savomart-api", "label": "Savomart stores API", "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "count": len(stores)}}
                f.write_text(json.dumps(res))
        except Exception:
            pass
    return res or {"stores": [{"name": n, "lat": a, "lng": b} for n, a, b in SAMPLE_STORES],
                   "meta": {"source": "sample", "label": "SAMPLE stores (API unreachable or token not set)", "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "count": len(SAMPLE_STORES)}}


def nearest_store_km(lat, lng, stores):
    ds = [geo.haversine_m(lat, lng, s["lat"], s["lng"]) for s in stores]
    return min(ds) / 1000 if ds else None
