"""
Sentinel corpus ingestion — reads all files from corpus/ and builds
the decision knowledge graph in Cognee Cloud.

Each source document (ADR, Slack export, PR record) is added separately
via cognee.add() so Cognee processes them as distinct nodes and can extract
cross-document relationships. cognify() then runs entity extraction and
graph construction across all staged documents.

corpus/
  adrs/   — Architecture Decision Records   (source_type: ADR)
  slack/  — Slack conversation exports      (source_type: Slack)
  prs/    — PR metadata                     (source_type: PR)
"""

import asyncio
from pathlib import Path
import cognee

CORPUS_DIR = Path(__file__).parent.parent / "corpus"
DATASET_NAME = "sentinel_decisions"


def _iter_corpus_files():
    """Yield (path, source_type) for every markdown file in corpus/."""
    subdir_to_type = {
        "adrs": "ADR",
        "slack": "Slack",
        "prs": "PR",
    }
    for subdir, source_type in subdir_to_type.items():
        folder = CORPUS_DIR / subdir
        for path in sorted(folder.glob("*.md")):
            yield path, source_type


async def ingest_corpus() -> None:
    files = list(_iter_corpus_files())
    print(f"→ Staging {len(files)} corpus file(s) into Cognee Cloud...")

    for path, source_type in files:
        content = path.read_text(encoding="utf-8")
        # Prepend source metadata so Cognee includes it in entity extraction
        tagged = f"[source_type: {source_type}] [file: {path.name}]\n\n{content}"
        await cognee.add(tagged, dataset_name=DATASET_NAME)
        print(f"  + {path.name} ({source_type})")

    print(f"\n→ Running cognify() — extracting entities and building graph...")
    await cognee.cognify(dataset_name=DATASET_NAME)
    print(f"✓ Graph built from {len(files)} documents in dataset '{DATASET_NAME}'.")


if __name__ == "__main__":
    from dotenv import load_dotenv
    from sentinel.connection import setup_cognee
    load_dotenv()

    async def _run():
        await setup_cognee()
        await ingest_corpus()

    asyncio.run(_run())