"""DB setup + models. SQLite by default (swap DATABASE_URL for Postgres/PostGIS in prod)."""
import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, JSON, Text
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./sitescout.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False)
Base = declarative_base()


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    role = Column(String)  # bd_manager | bd_executive | survey_manager | survey_executive


class Report(Base):  # Area Fitness Report (M1)
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    mode = Column(String)  # locality | pincode | grid
    query = Column(String, nullable=True)
    cells = Column(JSON)  # list of 500 m grid cell ids
    status = Column(String, default="pending")  # pending|running|done|failed
    progress = Column(Integer, default=0)
    stage = Column(String, default="Queued")
    error = Column(Text, nullable=True)
    score = Column(Float, nullable=True)
    rating = Column(String, nullable=True)
    result = Column(JSON, nullable=True)
    created_by = Column(Integer)
    created_at = Column(DateTime, default=now)
    finished_at = Column(DateTime, nullable=True)


class Property(Base):  # M2
    __tablename__ = "properties"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    lat = Column(Float, index=True)
    lng = Column(Float, index=True)
    details = Column(JSON)
    photos = Column(JSON, default=list)
    stage = Column(String, default="scouted")
    evaluation = Column(JSON, nullable=True)
    directive_id = Column(Integer, nullable=True)
    created_by = Column(Integer)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now)


class Event(Base):  # audit trail + activity feed
    __tablename__ = "events"
    id = Column(Integer, primary_key=True)
    ts = Column(DateTime, default=now)
    actor_id = Column(Integer)
    actor_name = Column(String)
    kind = Column(String)
    ref_type = Column(String)
    ref_id = Column(Integer)
    message = Column(Text)
    meta = Column(JSON, nullable=True)


class Directive(Base):  # BD manager -> executive "scout here"
    __tablename__ = "directives"
    id = Column(Integer, primary_key=True)
    report_id = Column(Integer)
    label = Column(String)
    lat = Column(Float)
    lng = Column(Float)
    executive_id = Column(Integer)
    note = Column(Text, nullable=True)
    status = Column(String, default="open")  # open | done
    created_by = Column(Integer)
    created_at = Column(DateTime, default=now)


class Survey(Base):  # M3 catchment study request
    __tablename__ = "surveys"
    id = Column(Integer, primary_key=True)
    property_id = Column(Integer, nullable=True)
    report_id = Column(Integer, nullable=True)
    title = Column(String)
    note = Column(Text, nullable=True)
    status = Column(String, default="requested")  # requested|in_progress|complete
    plan = Column(JSON)  # list of 250 m cell ids
    rollup = Column(JSON, nullable=True)
    requested_by = Column(Integer)
    created_at = Column(DateTime, default=now)


class Task(Base):  # one 250 m cell of a survey
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True)
    survey_id = Column(Integer, index=True)
    cell_id = Column(String, index=True)
    assignee_id = Column(Integer, nullable=True)
    status = Column(String, default="open")  # open|in_progress|done|reused
    data = Column(JSON, default=lambda: {"lanes": []})
    reused_from = Column(Integer, nullable=True)
    completed_at = Column(DateTime, nullable=True)


def d(o):
    """Row -> dict (datetimes as ISO-Z)."""
    out = {}
    for c in o.__table__.columns:
        v = getattr(o, c.name)
        out[c.name] = v.isoformat() + "Z" if isinstance(v, datetime) else v
    return out


def init_db():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if not db.query(User).count():
            for n, r in [("Priya (BD Manager)", "bd_manager"), ("Karthik (BD Executive)", "bd_executive"),
                         ("Meena (BD Executive)", "bd_executive"), ("Arun (Survey Manager)", "survey_manager"),
                         ("Divya (Survey Executive)", "survey_executive"), ("Ravi (Survey Executive)", "survey_executive")]:
                db.add(User(name=n, role=r))
            db.commit()
