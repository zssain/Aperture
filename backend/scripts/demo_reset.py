"""One-command demo reset: wipe tenant data, keep reference data, reseed.

Preserves migrations, the LIVE merchant catalogue and the embedding cache (reference
data — rebuilding them would need the embedding provider and possibly the network),
then reseeds the full demo book through the real decision pipeline.

Usage:  DEMO_SEED_ENABLED=true uv run python scripts/demo_reset.py
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.demo.seed import seed_demo
from sqlalchemy import text

# Everything except alembic_version, the merchant catalogue and the embedding cache.
_WIPE_TABLES = (
    "applicants",
    "applications",
    "assessments",
    "consents",
    "decision_changes",
    "decision_reasons",
    "decisions",
    "feature_snapshots",
    "human_reviews",
    "jobs",
    "ledger_entries",
    "ledger_events",
    "manipulation_findings",
    "model_versions",
    "notices",
    "outcomes",
    "policy_versions",
    "rate_limit_events",
    "recourse_options",
    "redecision_alerts",
    "retention_items",
    "sessions",
    "source_connections",
    "source_snapshots",
    "tenants",
    "users",
)


async def reset() -> None:
    if settings.environment.casefold() in {"production", "prod"}:
        raise RuntimeError("demo reset refused in production")
    started = time.monotonic()
    async with SessionLocal() as session:
        await session.execute(text(f"TRUNCATE {', '.join(_WIPE_TABLES)} CASCADE"))
        await session.commit()
    print(f"Wiped demo data ({time.monotonic() - started:.1f}s). Reseeding…")
    await seed_demo()
    print(f"Demo reset complete in {time.monotonic() - started:.1f}s.")


if __name__ == "__main__":
    asyncio.run(reset())
