"""Release gate for migrations, pgvector, catalogue, artifacts, audit chain and readiness."""

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal, check_db_ready
from app.models.merchant_catalog import MerchantCatalogEntry, MerchantCatalogVersion
from app.models.model_registry import ModelVersion
from app.services.audit.ledger import verify_chain
from sqlalchemy import select, text

ROOT = Path(__file__).resolve().parents[2]


def static_checks() -> dict[str, str]:
    required = (
        "docker-compose.prod.yml",
        "deploy/Dockerfile.api",
        "deploy/Dockerfile.frontend",
        "deploy/aws/task-definition.json",
        "docs/ARCHITECTURE.md",
        "docs/RUNBOOK.md",
    )
    missing = [name for name in required if not (ROOT / name).is_file()]
    if missing:
        raise RuntimeError(f"deployment artifacts missing: {missing}")
    task = json.loads((ROOT / "deploy/aws/task-definition.json").read_text())
    if task.get("requiresCompatibilities") != ["FARGATE"]:
        raise RuntimeError("task definition is not Fargate-compatible")
    return {"static_artifacts": "PASS", "task_definition": "PASS"}


def artifact_hash(uri: str) -> str | None:
    path = Path(uri)
    if not path.is_absolute():
        path = ROOT / path
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


async def online_checks() -> dict[str, str]:
    await check_db_ready()
    result = {"readiness": "PASS"}
    async with SessionLocal() as session:
        revision = await session.scalar(text("SELECT version_num FROM alembic_version"))
        if revision != "0010":
            raise RuntimeError(f"migration head mismatch: {revision}")
        result["migrations"] = "PASS"
        catalog = await session.scalar(
            select(MerchantCatalogVersion).where(MerchantCatalogVersion.status == "live")
        )
        if catalog is None:
            raise RuntimeError("no live merchant catalogue")
        entries = list(
            await session.scalars(
                select(MerchantCatalogEntry)
                .where(MerchantCatalogEntry.catalog_version_id == catalog.id)
            )
        )
        canonical = sorted(
            (
                {
                    "name": row.canonical_name,
                    "category": row.category,
                    "aliases": row.aliases,
                    "source": row.source_note,
                }
                for row in entries
            ),
            key=lambda row: json.dumps(row, sort_keys=True),
        )
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
        if digest != catalog.content_hash or len(entries) != catalog.entry_count:
            raise RuntimeError("catalogue content hash or entry count mismatch")
        result["catalogue"] = f"PASS:{catalog.version}:{digest}"
        for model in await session.scalars(select(ModelVersion)):
            if model.artifact_uri and model.artifact_hash:
                actual = await asyncio.to_thread(artifact_hash, model.artifact_uri)
                if actual is not None and actual != model.artifact_hash:
                    raise RuntimeError(f"model artifact hash mismatch: {model.name}")
        result["model_artifacts"] = "PASS"
        tenant_ids = list(await session.scalars(text("SELECT id FROM tenants")))
        for tenant_id in tenant_ids:
            chain = await verify_chain(session, tenant_id)
            if not chain["valid"]:
                raise RuntimeError(f"audit chain invalid for tenant {tenant_id}")
        result["audit_chains"] = "PASS"
    return result


async def main(static_only: bool) -> None:
    result = static_checks()
    if not static_only:
        result.update(await online_checks())
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--static", action="store_true")
    asyncio.run(main(parser.parse_args().static))
