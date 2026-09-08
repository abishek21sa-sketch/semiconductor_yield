"""
Persistence layer: SQLAlchemy models + engine/session setup. Defaults to a
local SQLite file so `RUN_DEMO.cmd` works with zero extra setup; set
DATABASE_URL to point at Postgres instead (docker-compose.yml does this for
the containerized run) -- same models, same Alembic migrations, either
backend.
"""
import json
import os
from datetime import datetime, timezone

from sqlalchemy import create_engine, String, Text, DateTime, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./fab_app.db")

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class AnalysisRun(Base):
    """One row per computed result the API has served -- yield analysis,
    a named scenario, the multi-period plan, or a dispatch run. This is
    what makes /api/history real: it reads back rows a prior request
    actually wrote, not synthesized data."""
    __tablename__ = "analysis_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_type: Mapped[str] = mapped_column(String(64), index=True)
    run_key: Mapped[str] = mapped_column(String(128))  # e.g. scenario name, or "default"
    status: Mapped[str] = mapped_column(String(32))
    summary_json: Mapped[str] = mapped_column(Text)  # small, serializable headline fields only
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "run_type": self.run_type,
            "run_key": self.run_key,
            "status": self.status,
            "summary": json.loads(self.summary_json),
            "created_at": self.created_at.isoformat(),
        }


def record_run(run_type: str, run_key: str, status: str, summary: dict):
    """Best-effort: persistence is an audit trail, not on the critical path
    -- a DB hiccup should never break a computation the caller already
    paid for, so failures here are logged, not raised."""
    session = SessionLocal()
    try:
        row = AnalysisRun(
            run_type=run_type, run_key=run_key, status=status,
            summary_json=json.dumps(summary, default=str),
        )
        session.add(row)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_history(run_type: str | None = None, limit: int = 50):
    session = SessionLocal()
    try:
        q = session.query(AnalysisRun).order_by(AnalysisRun.created_at.desc())
        if run_type:
            q = q.filter(AnalysisRun.run_type == run_type)
        return [r.to_dict() for r in q.limit(limit)]
    finally:
        session.close()


def ensure_schema():
    """Local/dev convenience: run Alembic migrations programmatically at
    startup so RUN_DEMO.cmd works with zero manual steps, while the
    migration scripts under alembic/versions/ remain the real source of
    truth (same ones a production deploy runs via `alembic upgrade head`)."""
    from pathlib import Path
    from alembic import command
    from alembic.config import Config

    base = Path(__file__).resolve().parent.parent
    cfg = Config(str(base / "alembic.ini"))
    cfg.set_main_option("script_location", str(base / "alembic"))
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(cfg, "head")
