"""
Day 2 — reversal detection on an incoming PR (the core product loop).

  1. ensure the decision graph exists (ingest the corpus once if empty)
  2. load a sample incoming PR (samples/incoming_pr_57_sync_email.md)
  3. detect_reversal() — recall the contradicted decision + reason, judge it
  4. render the GitHub comment Sentinel would post

The graph persists on disk between runs, so ingestion only happens the first time.

Run from the repo root:
    python scripts/day2_detect.py [path/to/pr.md]
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sentinel.connection import setup_cognee  # noqa: E402  (loads .env before cognee)
import cognee  # noqa: E402
from sentinel.comment import render_comment  # noqa: E402
from sentinel.detect import detect_reversal  # noqa: E402
from sentinel.ingest import ingest_corpus  # noqa: E402
from sentinel import sources  # noqa: E402

DEFAULT_PR_SLUG = "sync_email"  # the incoming reversal PR in the API snapshot


async def _node_count() -> int:
    from cognee.infrastructure.databases.graph import get_graph_engine

    nodes, _ = await (await get_graph_engine()).get_graph_data()
    return len(nodes)


async def _ensure_graph() -> None:
    if await _node_count() == 0:
        print("-> graph empty; ingesting corpus (one-time, slow on a local model)...")
        await ingest_corpus()
    else:
        print(f"-> reusing existing graph ({await _node_count()} nodes).")


async def main() -> None:
    # Accept a file path, an incoming-PR slug/number from the snapshot, or default to sync_email.
    arg = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PR_SLUG
    if Path(arg).is_file():
        pr_text, name = Path(arg).read_text(encoding="utf-8"), Path(arg).name
    else:
        pr_text, name = sources.incoming_text(arg), f"incoming PR '{arg}'"
        if not pr_text:
            print(f"No incoming PR '{arg}' in the API snapshot (.sentinel/api_snapshot.json). "
                  "Run scripts/seed_demo_repo.py to create the demo data, or pass a PR file path.")
            return

    await setup_cognee()
    await _ensure_graph()

    print(f"\n-> detecting reversals in: {name}")
    verdict = await detect_reversal(pr_text)

    print("\n=== VERDICT ===")
    print(f"  reverses_decision : {verdict.reverses_decision}")
    print(f"  decision_reference: {verdict.decision_reference}")
    print(f"  confidence        : {verdict.confidence:.0%}")

    print("\n=== PR COMMENT SENTINEL WOULD POST ===\n")
    print(render_comment(verdict))


if __name__ == "__main__":
    asyncio.run(main())
