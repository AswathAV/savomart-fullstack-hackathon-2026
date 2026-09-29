"""Area Fitness scoring (transparent, rule-based) + background report runner."""
import math, time
from . import geo, sources, ai
from .core import SessionLocal, Report, now

WEIGHTS = {"demand": .30, "footfall": .20, "competition": .20, "cannibalisation": .20, "affordability": .10}
LABELS = {"demand": "Household demand", "footfall": "Footfall generators", "competition": "Competition balance", "cannibalisation": "Distance from our stores", "affordability": "Affordability"}
sat = lambda x, k: 100 * x / (x + k) if x > 0 else 0.0


def cannibal_score(d):
    if d is None: return 60.0
    pts = [(0, 5), (.4, 10), (.8, 45), (1.2, 80), (2, 95), (3.5, 80), (6, 55), (12, 40)]
    for (a, sa), (b, sb) in zip(pts, pts[1:]):
        if d <= b: return sa + (sb - sa) * (d - a) / (b - a)
    return 40.0


def rating(s): return "Excellent" if s >= 75 else "Good" if s >= 60 else "Moderate" if s >= 45 else "Weak"


def score_signals(c, area_km2, loc, nearest_km):
    hh = loc["pop_km2"] / 3.8
    housing = c["housing"] / area_km2
    gen = (2 * c["education"] + 1.5 * c["health"] + c["office"] + 2 * c["transit"] + .5 * c["food"]) / area_km2
    comp = c["competitor"] / area_km2
    raw = {
        "demand": (.7 * sat(hh, 3500) + .3 * sat(housing, 40), f"~{hh:,.0f} households/km² (estimated, {loc['name']} ward) and {housing:.0f} mapped residential buildings/km²", "Census-style estimate (mock) + OSM"),
        "footfall": (sat(gen, 25), f"{gen:.0f} weighted footfall generators/km² (schools, transit, offices, clinics, eateries)", "OSM"),
        "competition": (100 * math.exp(-(((comp - 4) / 5) ** 2)), f"{comp:.1f} competing grocery/market outlets per km² (sweet spot ≈ 4: proves demand without saturation)", "OSM"),
        "cannibalisation": (cannibal_score(nearest_km), "no Savomart store data" if nearest_km is None else f"nearest Savomart store {nearest_km:.1f} km away", "Savomart stores API"),
        "affordability": (loc["income"] * 100, f"income index {loc['income']:.2f} for {loc['name']} (mock)", "Mock, replace with Census/NSSO"),
    }
    factors = [{"key": k, "label": LABELS[k], "score": round(v[0]), "weight": WEIGHTS[k], "contribution": round(v[0] * WEIGHTS[k], 1), "explain": v[1], "source": v[2]} for k, v in raw.items()]
    return {"total": round(sum(v[0] * WEIGHTS[k] for k, v in raw.items())), "factors": factors}


def _prog(db, r, pct, stage):
    r.progress, r.stage = pct, stage; db.commit()


def run_report(report_id):
    db = SessionLocal()
    r = db.get(Report, report_id)
    try:
        r.status, r.error = "running", None
        _prog(db, r, 10, "Preparing grid")
        cells = r.cells
        bbox = geo.bbox_of(cells, 0.001)
        _prog(db, r, 25, "Fetching OpenStreetMap features")
        osm = sources.fetch_features(bbox)
        _prog(db, r, 50, "Fetching Savomart stores")
        st = sources.fetch_stores()
        _prog(db, r, 65, "Scoring cells and area")
        per = {c: {k: 0 for k in sources.CATS} for c in cells}
        for f in osm["features"]:
            cid = geo.cell_id(f["lat"], f["lng"], 500)
            if cid in per: per[cid][f["cat"]] += 1
        cell_out, tot = [], {k: 0 for k in sources.CATS}
        near_list = []
        for cid in cells:
            la, ln = geo.cell_center(cid)
            nk = sources.nearest_store_km(la, ln, st["stores"]); near_list.append(nk)
            s = score_signals(per[cid], .25, geo.nearest_place(la, ln), nk)
            cell_out.append({"id": cid, "lat": la, "lng": ln, "score": s["total"], "counts": per[cid], "nearest_store_km": None if nk is None else round(nk, 2), "factors": s["factors"]})
            for k in tot: tot[k] += per[cid][k]
        clat, clng = sum(c["lat"] for c in cell_out) / len(cell_out), sum(c["lng"] for c in cell_out) / len(cell_out)
        known = [x for x in near_list if x is not None]
        avg_near = sum(known) / len(known) if known else None
        area_km2 = len(cells) * .25
        agg = score_signals(tot, area_km2, geo.nearest_place(clat, clng), avg_near)
        ranked = sorted(cell_out, key=lambda c: -c["score"])[:3]
        hotspots = []
        for i, c in enumerate(ranked, 1):
            top = sorted(c["factors"], key=lambda f: -f["contribution"])[:2]
            hotspots.append({"rank": i, "cell_id": c["id"], "lat": c["lat"], "lng": c["lng"], "score": c["score"], "reason": "; ".join(f["explain"] for f in top)})
        srt = sorted(agg["factors"], key=lambda f: -f["score"])
        near_txt = f"{avg_near:.1f}" if avg_near is not None else "unknown"
        place = geo.nearest_place(clat, clng)["name"]
        facts = {"area": r.name, "score": agg["total"], "rating": rating(agg["total"]), "strongest": {"factor": srt[0]["label"], "score": srt[0]["score"], "detail": srt[0]["explain"]},
                 "weakest": {"factor": srt[-1]["label"], "score": srt[-1]["score"], "detail": srt[-1]["explain"]}, "avg_km_to_nearest_savomart_store": near_txt,
                 "cells_analysed": len(cells), "top_hotspot": {"score": hotspots[0]["score"], "why": hotspots[0]["reason"]}}
        fallback = (f"{r.name} scores {agg['total']} out of 100 ({rating(agg['total'])}) for a Savomart neighbourhood store. "
                    f"The strongest signal is {srt[0]['label'].lower()} ({srt[0]['score']}): {srt[0]['explain']}. The weakest is {srt[-1]['label'].lower()} ({srt[-1]['score']}): {srt[-1]['explain']}. "
                    f"Scout first at hotspot 1 (cell score {hotspots[0]['score']}).")
        _prog(db, r, 85, "Writing explanation")
        narrative = ai.narrate(facts, fallback)
        r.result = {"area": {"cells": len(cells), "km2": area_km2, "center": [clat, clng], "nearest_locality": place},
                    "metrics": tot, "factors": agg["factors"], "cells": cell_out, "hotspots": hotspots, "stores": st["stores"], "narrative": narrative,
                    "provenance": {"osm": osm["meta"], "stores": st["meta"], "demographics": {"label": "MOCK ward-level estimates (see geo.py); replace with Census of India", "source": "mock"},
                                   "scoring_version": "v1", "weights": WEIGHTS, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}}
        r.score, r.rating = agg["total"], rating(agg["total"])
        r.status, r.progress, r.stage, r.finished_at = "done", 100, "Done", now()
        db.commit()
    except Exception as e:
        db.rollback(); r = db.get(Report, report_id)
        r.status, r.error, r.stage = "failed", f"{type(e).__name__}: {e}", f"Failed at: {r.stage}"; db.commit()
    finally:
        db.close()
