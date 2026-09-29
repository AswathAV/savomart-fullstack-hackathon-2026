"""Property evaluation (public data around the pin + executive's field input + any catchment study data) and survey roll-ups."""
import math
from datetime import timedelta
from sqlalchemy import select
from . import geo, sources
from .analysis import score_signals, sat
from .core import Task, Survey, now

FRESH_DAYS = 90
clamp = lambda x: max(0, min(100, x))


def rollup(lanes, cells):
    n = len(lanes)
    if not n: return None
    avg = lambda k: sum(float(l.get(k) or 0) for l in lanes) / n
    fh = avg("footfall_10min") * 6
    hh = sum(float(l.get("households_est") or 0) for l in lanes)
    comp_per_lane = avg("competitors")
    inc = sum({"low": .4, "mid": .7, "high": 1.0}.get(l.get("income"), .6) for l in lanes) / n
    score = .35 * sat(fh, 300) + .30 * sat(hh, 1500) + .20 * 100 * math.exp(-(((comp_per_lane - .8) / 1.2) ** 2)) + .15 * inc * 100
    return {"score": round(score), "lanes": n, "cells": cells, "footfall_per_hour": round(fh), "households_est": round(hh), "competitors_per_lane": round(comp_per_lane, 1),
            "income_mix": round(inc, 2), "insights": [f"{n} lanes surveyed across {cells} cells: about {round(fh)} people/hour walk past per lane on average.",
                                                    f"Roughly {round(hh)} households counted along surveyed lanes.", f"{comp_per_lane:.1f} competing outlets per lane on average."]}


def catchment_for(db, lat, lng, radius=500):
    """Reuse rule: any DONE/REUSED 250 m cell whose centre is within radius of the point and was captured within FRESH_DAYS. Needs >=3 cells to count."""
    cut = now() - timedelta(days=FRESH_DAYS)
    tasks = db.scalars(select(Task).where(Task.status.in_(["done", "reused"]), Task.completed_at >= cut)).all()
    used = [t for t in tasks if geo.haversine_m(lat, lng, *geo.cell_center(t.cell_id)) <= radius]
    if len({t.cell_id for t in used}) < 3: return None
    seen, lanes = set(), []
    for t in used:
        if t.cell_id in seen: continue
        seen.add(t.cell_id); lanes += t.data.get("lanes", [])
    ro = rollup(lanes, len(seen))
    if not ro: return None
    ro["freshest"] = max(t.completed_at for t in used).isoformat() + "Z"; ro["oldest"] = min(t.completed_at for t in used).isoformat() + "Z"
    return ro


def evaluate(db, p):
    d = p.details
    osm = sources.fetch_features((p.lat - .0055, p.lng - .0055 / math.cos(math.radians(13)), p.lat + .0055, p.lng + .0055 / math.cos(math.radians(13))))
    st = sources.fetch_stores()
    counts = {k: 0 for k in sources.CATS}
    for f in osm["features"]:
        if geo.haversine_m(p.lat, p.lng, f["lat"], f["lng"]) <= 500: counts[f["cat"]] += 1
    loc = geo.nearest_place(p.lat, p.lng)
    nk = sources.nearest_store_km(p.lat, p.lng, st["stores"])
    sig = score_signals(counts, math.pi * .25, loc, nk)
    cat = catchment_for(db, p.lat, p.lng)
    location = sig["total"] if not cat else round(.5 * sig["total"] + .5 * cat["score"])
    psf = d["rent"] / d["area_sqft"]
    ratio = psf / loc["rent_psf"]
    commercial = clamp(100 - max(0, ratio - .8) * 125)
    phys = 50 + (20 if 400 <= d["area_sqft"] <= 1200 else 10 if 300 <= d["area_sqft"] <= 1800 else 0)
    phys += 15 if (d.get("frontage_ft") or 0) >= 15 else 8 if (d.get("frontage_ft") or 0) >= 10 else 0
    phys += (10 if d.get("floor", 0) == 0 else 0) + (5 if d.get("parking") else 0) + (5 if (d.get("road_width_ft") or 0) >= 20 else 0)
    phys = clamp(phys)
    total = round(.5 * location + .3 * commercial + .2 * phys)
    rec = "PROCEED" if total >= 70 else "REVIEW" if total >= 50 else "REJECT"
    insights, risks = [], []
    for f in sig["factors"]:
        (insights if f["score"] >= 70 else risks if f["score"] < 40 else []).append(f"{f['label']}: {f['explain']} (score {f['score']})")
    (insights if ratio <= 1 else risks).append(f"Rent is ₹{psf:.0f}/sqft vs ~₹{loc['rent_psf']}/sqft benchmark for {loc['name']} ({ratio:.2f}x, benchmark is mock)")
    if (d.get("frontage_ft") or 0) < 10: risks.append("Narrow or unknown frontage limits visibility")
    if nk is not None and nk < .6: risks.append(f"Only {nk:.1f} km from an existing Savomart store, so cannibalisation risk is high")
    if cat: insights.append(f"Catchment study data used: {cat['footfall_per_hour']} people/hour per lane, study score {cat['score']}")
    else: risks.append("No catchment study yet; location score relies on public data only")
    return {"status": "done", "score": total, "recommendation": rec, "breakdown": {"location": round(location), "commercial": round(commercial), "physical": round(phys)},
            "rent_psf": round(psf, 1), "benchmark_psf": loc["rent_psf"], "nearest_store_km": None if nk is None else round(nk, 2), "counts_500m": counts,
            "insights": insights, "risks": risks, "catchment": cat, "catchment_used": bool(cat),
            "data": {"osm": osm["meta"], "stores": st["meta"], "evaluated_at": now().isoformat() + "Z"}}
