"""
Sentinel corpus ingestion — reads corpus/ and builds the decision knowledge
graph in LOCAL self-hosted Cognee (Ollama-backed; nothing leaves the laptop).

This is the `remember` phase, done as two steps:
  cognee.add()      — stage each document into the dataset
  cognee.cognify()  — extract entities and build the graph across all documents

Each ADR / PR / Slack file is added separately and tagged with its source type so
cognify can extract *cross-document* relationships — the multi-hop chain Sentinel
relies on (PR --reverses--> EngineeringDecision --justified_by--> ArchitecturalReason).

corpus/
  adrs/   — Architecture Decision Records   (source_type: ADR)
  slack/  — static "Slack" exports          (source_type: Slack)
  prs/    — PR metadata                      (source_type: PR)
"""

from pathlib import Path
from uuid import UUID, uuid5

import cognee
from cognee.tasks.ingestion.data_item import DataItem

CORPUS_DIR = Path(__file__).parent.parent / "corpus"
DATASET_NAME = "sentinel_decisions"

_SUBDIR_TO_TYPE = {"adrs": "ADR", "slack": "Slack", "prs": "PR"}

# Fixed namespace so data_ids are stable across runs — lets resolve.py do
# selective forget by data_id without querying the DB each time.
_SENTINEL_NS = UUID("7c9e6679-7425-40de-944b-e07fc1f90ae7")


def corpus_file_data_id(filename: str) -> UUID:
    """Return the stable data_id for a corpus file given its basename."""
    return uuid5(_SENTINEL_NS, filename)


def _iter_corpus_files():
    """Yield (path, source_type) for every markdown file in corpus/."""
    for subdir, source_type in _SUBDIR_TO_TYPE.items():
        for path in sorted((CORPUS_DIR / subdir).glob("*.md")):
            yield path, source_type


async def ingest_corpus() -> None:
    files = list(_iter_corpus_files())
    print(f"-> Staging {len(files)} corpus file(s) into local Cognee...")

    for path, source_type in files:
        content = path.read_text(encoding="utf-8")
        # Prepend source metadata so Cognee includes it during entity extraction.
        tagged = f"[source_type: {source_type}] [file: {path.name}]\n\n{content}"
        # DataItem gives each file a stable, addressable data_id (for selective forget)
        # and a human-readable label (the filename) visible in datasets.list_data().
        item = DataItem(
            data=tagged,
            label=path.name,
            data_id=corpus_file_data_id(path.name),
        )
        await cognee.add(item, dataset_name=DATASET_NAME)
        print(f"   + {path.name} ({source_type})")

    print("-> cognify() — extracting entities + building graph (slow on a local model)...")
    await cognee.cognify(datasets=[DATASET_NAME])
    print(f"OK: graph built from {len(files)} documents in dataset '{DATASET_NAME}'.")


if __name__ == "__main__":
    import asyncio

    from sentinel.connection import setup_cognee

    async def _run():
        await setup_cognee()
        await ingest_corpus()

    asyncio.run(_run())
