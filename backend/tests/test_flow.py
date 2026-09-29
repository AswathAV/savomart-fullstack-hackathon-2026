import os
os.environ["OFFLINE_MODE"] = "1"; os.environ["DATABASE_URL"] = "sqlite:///./test.db"; os.environ["CACHE_DIR"] = ".cache_test"
from fastapi.testclient import TestClient
from app.main import app
from app import geo


def h(uid): return {"X-User-Id": str(uid)}


def test_core_loop():
    with TestClient(app) as c:
        r = c.post("/api/resolve", json={"mode": "pincode", "query": "600042"}, headers=h(1)).json()
        rep = c.post("/api/reports", json={"name": r["name"], "mode": "pincode", "cells": r["cells"]}, headers=h(1)).json()
        got = c.get(f"/api/reports/{rep['id']}", headers=h(1)).json()
        assert got["status"] == "done" and got["result"]["hotspots"]  # background task runs inline in TestClient
        assert c.post("/api/reports", json={"cells": ["500:1:1"]}, headers=h(1)).status_code == 422
        assert c.post("/api/reports", json={"cells": r["cells"]}, headers=h(2)).status_code == 403
        body = {"name": "Test shop", "lat": 12.9822, "lng": 80.2195, "rent": 60000, "area_sqft": 800, "frontage_ft": 16}
        p = c.post("/api/properties", json=body, headers=h(2)).json()
        assert c.post("/api/properties", json=body, headers=h(2)).status_code == 409
        assert c.post("/api/properties", json={**body, "lat": 20}, headers=h(2)).status_code == 422
        assert c.post("/api/properties", json={**body, "lat": 12.99, "rent": 5}, headers=h(2)).status_code == 422
        det = c.get(f"/api/properties/{p['id']}", headers=h(1)).json()
        assert det["evaluation"]["recommendation"] in ("PROCEED", "REVIEW", "REJECT")
        assert c.post(f"/api/properties/{p['id']}/transition", json={"to": "approved", "reason": "skip"}, headers=h(1)).status_code == 400
        s = c.post("/api/surveys", json={"property_id": p["id"]}, headers=h(1)).json()
        c.post(f"/api/surveys/{s['id']}/split", headers=h(4))
        c.post(f"/api/surveys/{s['id']}/assign", json={"executive_ids": [5, 6]}, headers=h(4))
        for t in c.get("/api/tasks", headers=h(5)).json() + c.get("/api/tasks", headers=h(6)).json():
            uid = 5 if t["assignee_id"] == 5 else 6
            assert c.put(f"/api/tasks/{t['id']}", json={"submit": True, "lanes": [{"name": "Main St", "footfall_10min": 60, "households_est": 80, "competitors": 1}]}, headers=h(uid)).status_code == 200
        fin = c.get(f"/api/surveys/{s['id']}", headers=h(4)).json()
        assert fin["status"] == "complete" and fin["rollup"]["score"] > 0
        assert c.get(f"/api/properties/{p['id']}", headers=h(1)).json()["evaluation"]["catchment_used"]


def test_grid_partition():
    cells = geo.cells_in_radius(13.0, 80.2, 1000)
    assert len(cells) == len(set(cells))
    kids = {k for c in cells for k in geo.subdivide(c)}
    assert len(kids) == 4 * len(cells)  # non-overlapping, full coverage
