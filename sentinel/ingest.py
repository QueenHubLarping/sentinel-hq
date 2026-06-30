"""
Sentinel `remember` — build the decision memory graph in self-hosted Cognee.

Memory is reconstructed from the team's REAL GitHub history — merged PRs (the WHAT) and
their linked issues (the WHY) — pulled from the GitHub API (see sentinel.sources). There is
NO hand-authored markdown corpus and no `memory/` directory. For offline / demo runs the
API responses are replayed from a cached JSON snapshot (`.sentinel/api_snapshot.json`), so a
judge never has to trust the network on stage — but every byte still originated from the API.

  cognee.add()      — stage each PR / issue doc (stable, addressable data_id)
  cognee.cognify()  — extract entities + typed cross-document edges; the multi-hop chain:
                      incoming PR --reverses--> EngineeringDecision(PR) --justified_by--> Incident(Issue)

The rationale lives in the incident ISSUE, never in the PR diff — that separation is what
makes the SPINE-1 graph-only hop real (the incoming PR shares no words and no #ref with the
issue holding the why).
"""

import os
from pathlib import Path
from uuid import UUID, uuid5

import cognee
from cognee.tasks.ingestion.data_item import DataItem

# Legacy path constant — the bundled markdown corpus is removed; this only anchors the
# improve-loop's dismissal-file fallback (see adr_dir) and resolve's dormant ADR path.
CORPUS_DIR = Path(__file__).parent.parent / "corpus"
DATASET_NAME = "sentinel_decisions"

# Fixed namespace so data_ids are stable across runs — lets resolve.py do selective forget
# by data_id, and the retired-skip work, without querying internal Cognee dataset APIs.
_SENTINEL_NS = UUID("7c9e6679-7425-40de-944b-e07fc1f90ae7")


def corpus_file_data_id(label: str) -> UUID:
    """Return the stable data_id for an ingested document given its label (e.g. 'PR-42.md').

    Deterministic so selective forget (resolve.py) and the retired-skip target the same id
    that ingest assigned at add() time, across CI runner restarts.
    """
    return uuid5(_SENTINEL_NS, label)


def prs_dir() -> Path:
    """Legacy path constant (bundled PR markdown removed; kept for resolve's glob fallback)."""
    return CORPUS_DIR / "prs"


def adr_dir() -> Path:
    """Directory the improve-loop's durable dismissal file falls back to.

    Resolution: SENTINEL_ADR_DIR override → $GITHUB_WORKSPACE → CORPUS_DIR/adrs. (The ADR
    *corpus* is gone; this only locates the small `.sentinel-dismissed` file in CI/dev.)
    """
    explicit = os.environ.get("SENTINEL_ADR_DIR")
    if explicit:
        return Path(explicit)
    workspace = os.environ.get("GITHUB_WORKSPACE")
    if workspace:
        return Path(workspace)
    return CORPUS_DIR / "adrs"


async def ingest_corpus() -> None:
    """Stage merged PRs + linked issues (from the API or the cached snapshot) and cognify.

    Only MERGED PRs become memory (the establishing decisions); open PRs are the changes
    under review, not history. Issues carry the rationale. A retired decision (recorded in
    `.sentinel/retired.json` by '/sentinel intentional') is skipped — this is how forget
    takes durable effect on an ephemeral runner with no graph persistence.
    """
    from sentinel import sources
    from sentinel.retired import retired_data_ids, retired_pr_numbers

    prs, issues = sources.gather_memory()
    merged = [pr for pr in prs if pr.get("merged_at")]
    src = "live GitHub API" if sources.refreshing_live() else "cached API snapshot"
    print(f"-> Staging {len(merged)} PR(s) + {len(issues)} issue(s) into Cognee ({src})...")

    retired_nums = retired_pr_numbers()
    retired_ids = retired_data_ids()

    staged = 0
    for pr in merged:
        label, content = sources.pr_to_doc(pr)
        data_id = corpus_file_data_id(label)
        num = pr.get("number")
        if str(data_id) in retired_ids or (isinstance(num, int) and num in retired_nums):
            print(f"   - skipping {label} (decision retired via /sentinel intentional)")
            continue
        await cognee.add(
            DataItem(data=content, label=label, data_id=data_id), dataset_name=DATASET_NAME
        )
        staged += 1
        print(f"   + {label} (PR: \"{(pr.get('title') or '')[:48]}\")")

    for issue in issues:
        label, content = sources.issue_to_doc(issue)
        await cognee.add(
            DataItem(data=content, label=label, data_id=corpus_file_data_id(label)),
            dataset_name=DATASET_NAME,
        )
        staged += 1
        print(f"   + {label} (Issue: \"{(issue.get('title') or '')[:48]}\")")

    if staged == 0:
        print(
            "   (!) nothing to ingest — no API snapshot and no GitHub creds. "
            "Run scripts/seed_demo_repo.py to create the demo data + snapshot, "
            "or set GITHUB_REPOSITORY + GITHUB_TOKEN to fetch live."
        )
        return

    print(f"-> cognify() — extracting entities + building graph from {staged} doc(s)...")
    await cognee.cognify(datasets=[DATASET_NAME])
    print(f"OK: graph built from {staged} documents in dataset '{DATASET_NAME}'.")


if __name__ == "__main__":
    import asyncio

    from sentinel.connection import setup_cognee

    async def _run():
        await setup_cognee()
        await ingest_corpus()

    asyncio.run(_run())
