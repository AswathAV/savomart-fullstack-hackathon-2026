import os, math
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Optional
from fastapi import FastAPI, Depends, Header, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.orm import Session
from . import geo, analysis, evaluation
from .core import *


@asynccontextmanager
async def lifespan(_):
    init_db(); yield

app = FastAPI(title="Savo SiteScout API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","), allow_methods=["*"], allow_headers=["*"])


def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()


def auth(*roles):
    def dep(x_user_id: int = Header(None), db: Session = Depends(get_db)):
        if x_user_id is None: raise HTTPException(401, "Pick a user (X-User-Id header missing)")
        u = db.get(User, x_user_id)
        if not u: raise HTTPException(401, "Unknown user")
        if roles and u.role not in roles: raise HTTPException(403, f"This action needs role: {' / '.join(roles)}")
        return u
    return dep

MGR, EXEC, SMGR, SEXEC = "bd_manager", "bd_executive", "survey_manager", "survey_executive"


def log(db, u, kind, ref_type, ref_id, msg, meta=None):
    db.add(Event(actor_id=u.id if u else None, actor_name=u.name if u else "System", kind=kind, ref_type=ref_type, ref_id=ref_id, message=msg, meta=meta))


@app.get("/api/health")
def health(): return {"ok": True}


@app.get("/api/users")
def users(db: Session = Depends(get_db)): return [d(u) for u in db.scalars(select(User))]


@app.get("/api/places")
def places(q: str = ""): return geo.search_places(q)


class ResolveIn(BaseModel):
    mode: str
    query: str


@app.post("/api/resolve")
def resolve(b: ResolveIn, u=Depends(auth())):
    hits = geo.search_places(b.query)
    if not hits or not b.query.strip(): raise HTTPException(404, "No locality or pincode matches. Try 'Velachery' or '600042', or pick grid cells on the map.")
    p = hits[0]
    return {"name": f"{p['name']} · {p['pincode']}", "center": [p["lat"], p["lng"]], "cells": geo.cells_in_radius(p["lat"], p["lng"], 1200)}


@app.get("/api/stores")
def stores(u=Depends(auth())):
    from . import sources
    return sources.fetch_stores()


# ---------- M1 reports ----------
class ReportIn(BaseModel):
    name: str = ""
    mode: str = "grid"
    query: Optional[str] = None
    cells: list[str] = Field(min_length=1, max_length=80)


def _summary(r): x = d(r); x.pop("result"); x.pop("cells"); x["provenance"] = (r.result or {}).get("provenance"); x["cell_count"] = len(r.cells); return x


@app.post("/api/reports")
def create_report(b: ReportIn, bg: BackgroundTasks, u=Depends(auth(MGR)), db: Session = Depends(get_db)):
    try:
        for c in b.cells:
            if geo.parse_cell(c)[0] != 500 or not geo.in_chennai(*geo.cell_center(c)): raise ValueError
    except Exception:
        raise HTTPException(422, "Selection includes cells outside Chennai or with an invalid id")
    r = Report(name=b.name or f"Custom grid ({len(b.cells)} cells)", mode=b.mode, query=b.query, cells=b.cells, created_by=u.id)
    db.add(r); db.flush(); log(db, u, "report_created", "report", r.id, f"requested area analysis “{r.name}”"); db.commit()
    bg.add_task(analysis.run_report, r.id)
    return _summary(r)


@app.get("/api/reports")
def reports(u=Depends(auth(MGR, EXEC, SMGR)), db: Session = Depends(get_db)):
    return [_summary(r) for r in db.scalars(select(Report).order_by(desc(Report.id)))]


@app.get("/api/reports/{rid}")
def report(rid: int, u=Depends(auth(MGR, EXEC, SMGR)), db: Session = Depends(get_db)):
    r = db.get(Report, rid)
    if not r: raise HTTPException(404, "Report not found")
    return d(r)


@app.post("/api/reports/{rid}/retry")
def retry(rid: int, bg: BackgroundTasks, u=Depends(auth(MGR)), db: Session = Depends(get_db)):
    r = db.get(Report, rid)
    if not r or r.status != "failed": raise HTTPException(400, "Only failed reports can be retried")
    r.status, r.progress, r.stage = "pending", 0, "Queued"; db.commit(); bg.add_task(analysis.run_report, rid)
    return _summary(r)


# ---------- directives ----------
class DirectiveIn(BaseModel):
    report_id: int
    label: str
    lat: float
    lng: float
    executive_id: int
    note: str = ""


@app.post("/api/directives")
def directive(b: DirectiveIn, u=Depends(auth(MGR)), db: Session = Depends(get_db)):
    ex = db.get(User, b.executive_id)
    if not ex or ex.role != EXEC: raise HTTPException(422, "Assignee must be a BD executive")
    x = Directive(**b.model_dump(), created_by=u.id); db.add(x); db.flush()
    log(db, u, "directive", "directive", x.id, f"asked {ex.name} to scout {b.label}"); db.commit()
    return d(x)


@app.get("/api/directives")
def directives(u=Depends(auth(MGR, EXEC)), db: Session = Depends(get_db)):
    q = select(Directive).order_by(desc(Directive.id))
    if u.role == EXEC: q = q.where(Directive.executive_id == u.id)
    return [d(x) for x in db.scalars(q)]


# ---------- M2 properties ----------
STAGES = ["scouted", "shortlisted", "study_requested", "under_review", "approved", "rejected"]
ALLOWED = {"scouted": ["shortlisted", "rejected"], "shortlisted": ["study_requested", "under_review", "rejected"], "study_requested": ["under_review", "rejected"],
           "under_review": ["approved", "rejected", "shortlisted"], "approved": [], "rejected": ["scouted"]}


class PropertyIn(BaseModel):
    name: str = Field(min_length=2)
    lat: float
    lng: float
    rent: float = Field(gt=0, description="Monthly rent in INR")
    area_sqft: float = Field(gt=0)
    deposit_months: Optional[float] = None
    frontage_ft: Optional[float] = Field(None, ge=0)
    floor: int = 0
    parking: bool = False
    road_width_ft: Optional[float] = None
    owner_phone: Optional[str] = None
    notes: str = ""
    photos: list[str] = Field(default_factory=list, max_length=5)
    directive_id: Optional[int] = None
    force: bool = False


def run_evaluation(pid):
    db = SessionLocal()
    try:
        p = db.get(Property, pid)
        try: p.evaluation = evaluation.evaluate(db, p)
        except Exception as e: p.evaluation = {"status": "failed", "error": f"{type(e).__name__}: {e}"}
        p.updated_at = now(); db.commit()
    finally: db.close()


@app.post("/api/properties")
def add_property(b: PropertyIn, bg: BackgroundTasks, u=Depends(auth(EXEC)), db: Session = Depends(get_db)):
    if not geo.in_chennai(b.lat, b.lng): raise HTTPException(422, "Pin is outside Chennai. Move the pin or use your location again.")
    psf = b.rent / b.area_sqft
    if not 10 <= psf <= 500: raise HTTPException(422, f"Rent looks wrong: ₹{psf:.0f}/sqft. Check rent (monthly, in ₹) and area (sqft).")
    if not b.force:
        for o in db.scalars(select(Property)):
            m = geo.haversine_m(b.lat, b.lng, o.lat, o.lng)
            if m <= 40 or (m <= 150 and o.name.strip().lower() == b.name.strip().lower()):
                raise HTTPException(409, {"message": f"Possible duplicate of “{o.name}” ({m:.0f} m away)", "existing_id": o.id})
    det = b.model_dump(exclude={"name", "lat", "lng", "photos", "directive_id", "force"})
    p = Property(name=b.name, lat=b.lat, lng=b.lng, details=det, photos=b.photos, directive_id=b.directive_id, created_by=u.id, evaluation={"status": "running"})
    db.add(p); db.flush()
    log(db, u, "property_added", "property", p.id, f"onboarded property “{p.name}”")
    if b.directive_id and (dr := db.get(Directive, b.directive_id)): dr.status = "done"
    cat = evaluation.catchment_for(db, p.lat, p.lng)
    if cat: log(db, None, "study_reused", "property", p.id, f"existing catchment data reused ({cat['cells']} cells, freshest {cat['freshest'][:10]})")
    db.commit(); bg.add_task(run_evaluation, p.id)
    return d(p)


def _prop(p, db=None, detail=False):
    x = d(p)
    if not detail: x["photos"] = x["photos"][:1]
    return x


@app.get("/api/properties")
def properties(u=Depends(auth(MGR, EXEC)), db: Session = Depends(get_db)):
    q = select(Property).order_by(desc(Property.id))
    if u.role == EXEC: q = q.where(Property.created_by == u.id)
    return [_prop(p) for p in db.scalars(q)]


@app.get("/api/properties/{pid}")
def property_detail(pid: int, u=Depends(auth(MGR, EXEC)), db: Session = Depends(get_db)):
    p = db.get(Property, pid)
    if not p or (u.role == EXEC and p.created_by != u.id): raise HTTPException(404, "Property not found")
    x = _prop(p, detail=True)
    x["history"] = [d(e) for e in db.scalars(select(Event).where(Event.ref_type == "property", Event.ref_id == pid).order_by(desc(Event.id)))]
    x["allowed"] = ALLOWED[p.stage] if u.role == MGR else []
    x["surveys"] = [{"id": s.id, "status": s.status} for s in db.scalars(select(Survey).where(Survey.property_id == pid))]
    return x


class TransitionIn(BaseModel):
    to: str
    reason: str = Field(min_length=3)


@app.post("/api/properties/{pid}/transition")
def transition(pid: int, b: TransitionIn, u=Depends(auth(MGR)), db: Session = Depends(get_db)):
    p = db.get(Property, pid)
    if not p: raise HTTPException(404, "Property not found")
    if b.to not in ALLOWED[p.stage]: raise HTTPException(400, f"Cannot move from {p.stage} to {b.to}. Allowed: {ALLOWED[p.stage] or 'none'}")
    log(db, u, "stage", "property", pid, f"moved “{p.name}” {p.stage} → {b.to}: {b.reason}", {"from": p.stage, "to": b.to, "reason": b.reason})
    p.stage, p.updated_at = b.to, now(); db.commit()
    return _prop(p, detail=True)


@app.post("/api/properties/{pid}/reevaluate")
def reevaluate(pid: int, u=Depends(auth(MGR)), db: Session = Depends(get_db)):
    p = db.get(Property, pid)
    if not p: raise HTTPException(404, "Property not found")
    p.evaluation = evaluation.evaluate(db, p); log(db, u, "reevaluated", "property", pid, f"re-evaluated “{p.name}”: {p.evaluation['recommendation']} ({p.evaluation['score']})"); db.commit()
    return _prop(p, detail=True)


# ---------- M3 surveys ----------
class SurveyIn(BaseModel):
    property_id: Optional[int] = None
    report_id: Optional[int] = None
    note: str = ""


@app.post("/api/surveys")
def request_survey(b: SurveyIn, u=Depends(auth(MGR)), db: Session = Depends(get_db)):
    if bool(b.property_id) == bool(b.report_id): raise HTTPException(422, "Request a study for either a property or an analysed area")
    if b.property_id:
        p = db.get(Property, b.property_id)
        if not p: raise HTTPException(404, "Property not found")
        cells = geo.cells_in_radius(p.lat, p.lng, 500, 250); title = f"Catchment study: {p.name}"
        if p.stage in ("scouted", "shortlisted"):
            log(db, u, "stage", "property", p.id, f"moved “{p.name}” {p.stage} → study_requested: catchment study requested", {"to": "study_requested"}); p.stage = "study_requested"
    else:
        r = db.get(Report, b.report_id)
        if not r or r.status != "done": raise HTTPException(400, "Area must be analysed first")
        cells = sorted({c for h in r.result["hotspots"] for c in geo.subdivide(h["cell_id"])}); title = f"Catchment study: {r.name} (top hotspots)"
    s = Survey(property_id=b.property_id, report_id=b.report_id, title=title, note=b.note, plan=cells, requested_by=u.id)
    db.add(s); db.flush(); log(db, u, "survey_requested", "survey", s.id, f"requested “{title}”"); db.commit()
    return d(s)


def _progress(db, sid):
    ts = db.scalars(select(Task).where(Task.survey_id == sid)).all()
    return {"total": len(ts), "done": sum(t.status in ("done", "reused") for t in ts), "reused": sum(t.status == "reused" for t in ts), "assigned": sum(t.assignee_id is not None for t in ts)}


@app.get("/api/surveys")
def surveys(u=Depends(auth(MGR, SMGR)), db: Session = Depends(get_db)):
    return [{**d(s), "plan": len(s.plan), "progress": _progress(db, s.id)} for s in db.scalars(select(Survey).order_by(desc(Survey.id)))]


@app.get("/api/surveys/{sid}")
def survey(sid: int, u=Depends(auth(MGR, SMGR)), db: Session = Depends(get_db)):
    s = db.get(Survey, sid)
    if not s: raise HTTPException(404, "Survey not found")
    x = d(s); x["progress"] = _progress(db, sid)
    x["tasks"] = [{**d(t), "lat": geo.cell_center(t.cell_id)[0], "lng": geo.cell_center(t.cell_id)[1], "bounds": geo.cell_bounds(t.cell_id)} for t in db.scalars(select(Task).where(Task.survey_id == sid).order_by(Task.id))]
    x["plan_cells"] = [{"id": c, "bounds": geo.cell_bounds(c)} for c in s.plan]
    if s.property_id and (p := db.get(Property, s.property_id)): x["property"] = {"id": p.id, "name": p.name, "lat": p.lat, "lng": p.lng}
    return x


@app.post("/api/surveys/{sid}/split")
def split(sid: int, u=Depends(auth(SMGR)), db: Session = Depends(get_db)):
    s = db.get(Survey, sid)
    if not s or s.status != "requested": raise HTTPException(400, "Survey already split")
    cut = now() - timedelta(days=evaluation.FRESH_DAYS)
    for c in sorted(s.plan, key=lambda c: geo.parse_cell(c)[1:]):
        old = db.scalars(select(Task).where(Task.cell_id == c, Task.status == "done", Task.completed_at >= cut).order_by(desc(Task.completed_at))).first()
        db.add(Task(survey_id=sid, cell_id=c, status="reused", data=old.data, reused_from=old.id, completed_at=old.completed_at) if old else Task(survey_id=sid, cell_id=c))
    s.status = "in_progress"; db.flush()
    pr = _progress(db, sid); log(db, u, "survey_split", "survey", sid, f"split “{s.title}” into {pr['total']} cell tasks ({pr['reused']} reused from fresh studies)")
    _finalize(db, s, u); db.commit()
    return survey(sid, u, db)


class AssignIn(BaseModel):
    executive_ids: list[int] = Field(min_length=1)


@app.post("/api/surveys/{sid}/assign")
def auto_assign(sid: int, b: AssignIn, u=Depends(auth(SMGR)), db: Session = Depends(get_db)):
    """Fair split: sort open cells geographically, cut into contiguous equal blocks so each executive walks one compact patch (no overlap)."""
    ts = sorted(db.scalars(select(Task).where(Task.survey_id == sid, Task.status == "open")).all(), key=lambda t: geo.parse_cell(t.cell_id)[1:])
    if not ts: raise HTTPException(400, "No open tasks to assign")
    k = len(b.executive_ids); size = math.ceil(len(ts) / k)
    for i, t in enumerate(ts): t.assignee_id = b.executive_ids[min(i // size, k - 1)]
    log(db, u, "survey_assigned", "survey", sid, f"assigned {len(ts)} tasks across {k} executives"); db.commit()
    return survey(sid, u, db)


class TaskAssign(BaseModel):
    assignee_id: int


@app.patch("/api/tasks/{tid}/assign")
def assign_task(tid: int, b: TaskAssign, u=Depends(auth(SMGR)), db: Session = Depends(get_db)):
    t = db.get(Task, tid)
    if not t or t.status in ("done", "reused"): raise HTTPException(400, "Task cannot be reassigned")
    t.assignee_id = b.assignee_id; db.commit(); return d(t)


@app.get("/api/tasks")
def tasks(u=Depends(auth(SMGR, SEXEC)), db: Session = Depends(get_db)):
    q = select(Task).where(Task.status != "reused")
    if u.role == SEXEC: q = q.where(Task.assignee_id == u.id)
    out = []
    for t in db.scalars(q.order_by(Task.id)):
        s = db.get(Survey, t.survey_id); c = geo.cell_center(t.cell_id)
        out.append({**d(t), "survey_title": s.title, "lat": c[0], "lng": c[1], "bounds": geo.cell_bounds(t.cell_id), "place": geo.nearest_place(*c)["name"]})
    return out


class Lane(BaseModel):
    name: str = Field(min_length=1)
    lane_width_ft: Optional[float] = Field(None, ge=0)
    footfall_10min: float = Field(ge=0)
    households_est: float = Field(0, ge=0)
    shops: int = Field(0, ge=0)
    competitors: int = Field(0, ge=0)
    income: str = "mid"
    notes: str = ""


class TaskData(BaseModel):
    lanes: list[Lane]
    submit: bool = False


@app.put("/api/tasks/{tid}")
def save_task(tid: int, b: TaskData, u=Depends(auth(SEXEC)), db: Session = Depends(get_db)):
    t = db.get(Task, tid)
    if not t or t.assignee_id != u.id: raise HTTPException(404, "Task not found")
    if t.status == "done": return d(t)  # idempotent for offline retries
    if b.submit and not b.lanes: raise HTTPException(422, "Capture at least one lane before submitting")
    t.data = {"lanes": [l.model_dump() for l in b.lanes]}; t.status = "in_progress"
    if b.submit:
        t.status, t.completed_at = "done", now(); s = db.get(Survey, t.survey_id)
        log(db, u, "task_done", "survey", s.id, f"completed cell {t.cell_id} of “{s.title}” ({len(b.lanes)} lanes)")
        _finalize(db, s, u)
    db.commit(); return d(t)


def _finalize(db, s, u):
    ts = db.scalars(select(Task).where(Task.survey_id == s.id)).all()
    if not ts or any(t.status not in ("done", "reused") for t in ts): return
    lanes = [l for t in ts for l in t.data.get("lanes", [])]
    s.rollup, s.status = evaluation.rollup(lanes, len(ts)), "complete"
    log(db, None, "survey_complete", "survey", s.id, f"“{s.title}” complete, catchment score {s.rollup['score'] if s.rollup else 'n/a'}")
    if s.property_id and (p := db.get(Property, s.property_id)):
        p.evaluation = evaluation.evaluate(db, p)
        log(db, None, "reevaluated", "property", p.id, f"re-evaluated with catchment data: {p.evaluation['recommendation']} ({p.evaluation['score']})")
        if p.stage == "study_requested": log(db, None, "stage", "property", p.id, f"moved “{p.name}” study_requested → under_review: study complete"); p.stage = "under_review"


@app.get("/api/activity")
def activity(u=Depends(auth()), db: Session = Depends(get_db)):
    return [d(e) for e in db.scalars(select(Event).order_by(desc(Event.id)).limit(40))]


# Serve the built React app from the same origin (one URL in production)
from pathlib import Path
from fastapi.staticfiles import StaticFiles
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="web")
