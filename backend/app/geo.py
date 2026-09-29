"""Grid maths + Chennai gazetteer. A fixed global grid means cells never overlap and are reusable across studies."""
import math

REF_LAT = 13.0
M = 111320.0
CHENNAI_BBOX = (12.80, 79.90, 13.30, 80.40)  # south, west, north, east

# Approximate, hand-estimated values. MOCK: replace pop_km2/income with Census 2011 ward data, rent_psf with broker data.
GAZETTEER = [
    ("T. Nagar", "600017", 13.0418, 80.2341, 30000, .75, 130), ("Velachery", "600042", 12.9815, 80.2180, 22000, .70, 95),
    ("Tambaram", "600045", 12.9249, 80.1000, 15000, .55, 65), ("Adyar", "600020", 13.0012, 80.2565, 20000, .80, 110),
    ("Anna Nagar", "600040", 13.0850, 80.2101, 21000, .85, 120), ("Porur", "600116", 13.0382, 80.1565, 14000, .65, 80),
    ("Perungudi", "600096", 12.9654, 80.2461, 12000, .70, 90), ("Mylapore", "600004", 13.0368, 80.2676, 27000, .80, 125),
    ("Guindy", "600032", 13.0067, 80.2206, 15000, .70, 100), ("Chromepet", "600044", 12.9516, 80.1462, 17000, .55, 70),
    ("Sholinganallur", "600119", 12.9010, 80.2279, 9000, .70, 75), ("Ambattur", "600053", 13.1143, 80.1548, 13000, .50, 60),
    ("Kodambakkam", "600024", 13.0521, 80.2255, 26000, .70, 115), ("Medavakkam", "600100", 12.9210, 80.1927, 11000, .55, 65),
    ("Pallavaram", "600043", 12.9675, 80.1491, 16000, .50, 65), ("Thiruvanmiyur", "600041", 12.9830, 80.2594, 18000, .80, 105),
    ("Perambur", "600011", 13.1150, 80.2330, 24000, .50, 75), ("Madipakkam", "600091", 12.9624, 80.1986, 19000, .60, 75),
]
PLACES = [dict(name=n, pincode=p, lat=la, lng=ln, pop_km2=pop, income=inc, rent_psf=rent) for n, p, la, ln, pop, inc, rent in GAZETTEER]


def dlat(size): return size / M
def dlng(size): return size / (M * math.cos(math.radians(REF_LAT)))


def cell_id(lat, lng, size=500):
    return f"{size}:{math.floor(lat / dlat(size))}:{math.floor(lng / dlng(size))}"


def parse_cell(cid):
    s, i, j = cid.split(":")
    return int(s), int(i), int(j)


def cell_bounds(cid):
    s, i, j = parse_cell(cid)
    return i * dlat(s), j * dlng(s), (i + 1) * dlat(s), (j + 1) * dlng(s)


def cell_center(cid):
    b = cell_bounds(cid)
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def haversine_m(a, b, c, d_):
    p1, p2 = math.radians(a), math.radians(c)
    x = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(d_ - b) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(x))


def cells_in_radius(lat, lng, r, size=500):
    i0, j0 = math.floor(lat / dlat(size)), math.floor(lng / dlng(size))
    n = int(r / size) + 2
    out = []
    for i in range(i0 - n, i0 + n + 1):
        for j in range(j0 - n, j0 + n + 1):
            cid = f"{size}:{i}:{j}"
            c = cell_center(cid)
            if haversine_m(lat, lng, c[0], c[1]) <= r:
                out.append(cid)
    return out


def subdivide(cid, size=250):
    b = cell_bounds(cid)
    h = [(b[0] + (b[2] - b[0]) * f, b[1] + (b[3] - b[1]) * g) for f in (.25, .75) for g in (.25, .75)]
    return [cell_id(a, c, size) for a, c in h]


def bbox_of(cells, pad=0.0):
    bs = [cell_bounds(c) for c in cells]
    return (min(b[0] for b in bs) - pad, min(b[1] for b in bs) - pad, max(b[2] for b in bs) + pad, max(b[3] for b in bs) + pad)


def in_chennai(lat, lng):
    s, w, n, e = CHENNAI_BBOX
    return s <= lat <= n and w <= lng <= e


def search_places(q):
    q = (q or "").strip().lower()
    return [p for p in PLACES if q and (q in p["name"].lower() or p["pincode"].startswith(q))][:8] if q else PLACES


def nearest_place(lat, lng):
    return min(PLACES, key=lambda p: haversine_m(lat, lng, p["lat"], p["lng"]))
