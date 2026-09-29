"""Demo data: python seed.py  (runs fully offline with simulated OSM data, clearly labelled in the UI)"""
import os
os.environ["OFFLINE_MODE"] = "1"
from app import core, analysis, geo, evaluation
from app.core import *
from app.main import run_evaluation

core.init_db()
db = SessionLocal()
if db.query(Report).count():
    print("Already seeded"); raise SystemExit
for name in ["Velachery", "Adyar", "Tambaram"]:
    p = geo.search_places(name)[0]
    r = Report(name=f"{p['name']} · {p['pincode']}", mode="locality", query=name, cells=geo.cells_in_radius(p["lat"], p["lng"], 1200), created_by=1)
    db.add(r); db.commit(); analysis.run_report(r.id)
rep = db.get(Report, 1)
h = rep.result["hotspots"][0]
db.add(Directive(report_id=1, label=f"Velachery hotspot #1", lat=h["lat"], lng=h["lng"], executive_id=2, note="Look for ground-floor units on the main road", created_by=1))
for i, (n, la, ln, rent, area, fr) in enumerate([("Corner shop near Velachery Main Rd", 12.9822, 80.2195, 78000, 850, 18), ("Ground floor, Taramani Link Rd", 12.9866, 80.2287, 120000, 700, 12)]):
    db.add(Property(name=n, lat=la, lng=ln, details={"rent": rent, "area_sqft": area, "frontage_ft": fr, "floor": 0, "parking": True, "road_width_ft": 24, "notes": "Demo data"}, photos=[], created_by=2, evaluation={"status": "running"}))
db.commit()
for p in db.query(Property): run_evaluation(p.id)
print("Seeded 3 reports, 2 properties, 1 directive. Users: 1=BD Manager 2,3=BD Exec 4=Survey Manager 5,6=Survey Exec")
