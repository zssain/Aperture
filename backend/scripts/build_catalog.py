import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.core.providers.registry import configured_registry
from app.db.session import SessionLocal
from app.services.catalog.builder import build_and_publish_catalog


async def main(version: str) -> None:
    provider = configured_registry().embedding(settings.embedding_provider)
    async with SessionLocal() as session:
        catalog = await build_and_publish_catalog(session, provider, version=version)
        print(f"published {catalog.version} {catalog.content_hash} ({catalog.entry_count} entries)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    asyncio.run(main(parser.parse_args().version))
