"""Print the demo case ids and URLs the runbook needs (Meera fraud, Kabir flip).

Usage:  uv run python scripts/demo_ids.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.models.applicant import Applicant
from app.models.application import Application
from sqlalchemy import select

_SPA = "http://localhost:5173"
_LABELLED = {
    "APL-1088": ("Meera Joshi (fraud story)", "?tab=verification"),
    "APL-1076": ("Kabir Shaikh (live-flip target)", ""),
}


async def main() -> None:
    async with SessionLocal() as session:
        for ref, (label, suffix) in _LABELLED.items():
            applicant = await session.scalar(
                select(Applicant).where(Applicant.external_ref == ref)
            )
            if applicant is None:
                print(f"{label}: not seeded — run `make demo-reset`")
                continue
            application = await session.scalar(
                select(Application).where(Application.applicant_id == applicant.id)
            )
            if application is None:
                print(f"{label}: applicant present but no application")
                continue
            print(f"{label:34s} {_SPA}/cases/{application.id}{suffix}")


if __name__ == "__main__":
    asyncio.run(main())
