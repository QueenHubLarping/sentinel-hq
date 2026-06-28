"""
Sentinel GitHub Action entrypoint.

On a PR: load the PR, ensure the decision graph exists, detect reversals, render the
comment. In dry-run mode (default) it just prints + writes the job summary — no token,
no network. In post mode it comments on the PR via the GitHub API.

Env:
  SENTINEL_MODE     dry-run (default) | post
  SENTINEL_PR_FILE  optional path to a PR markdown file (testing); else GitHub event
  GITHUB_TOKEN      required only for mode=post

Sentinel is advisory (detective, not gatekeeper): it never fails the build.
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sentinel.connection import setup_cognee  # noqa: E402
import cognee  # noqa: E402
from sentinel.comment import render_comment  # noqa: E402
from sentinel.detect import detect_reversal  # noqa: E402
from sentinel.github_pr import load_pr_text, post_comment  # noqa: E402
from sentinel.ingest import ingest_corpus  # noqa: E402


async def _node_count() -> int:
    from cognee.infrastructure.databases.graph import get_graph_engine

    nodes, _ = await (await get_graph_engine()).get_graph_data()
    return len(nodes)


def _write_summary(comment: str) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        Path(summary_path).write_text(comment, encoding="utf-8")


async def main() -> int:
    mode = os.environ.get("SENTINEL_MODE", "dry-run")
    pr_file = os.environ.get("SENTINEL_PR_FILE") or (sys.argv[1] if len(sys.argv) > 1 else None)

    pr_text = load_pr_text(pr_file)

    try:
        await setup_cognee()
    except RuntimeError as exc:
        msg = (
            f"⚠️ **Sentinel: configuration error** — {exc}\n\n"
            "Sentinel cannot run; skipping check. Fix the error above and re-run."
        )
        print(msg)
        _write_summary(msg)
        return 0  # advisory: never fail the build

    if await _node_count() == 0:
        print("-> decision graph empty; ingesting corpus (one-time)...")
        await ingest_corpus()

    verdict = await detect_reversal(pr_text)
    comment = render_comment(verdict)

    print("\n" + comment + "\n")
    _write_summary(comment)

    if verdict.reverses_decision:
        # GitHub Actions annotation — surfaces in the PR checks UI.
        print(f"::warning title=Sentinel::This PR reverses {verdict.decision_reference}")
        if mode == "post":
            post_comment(comment)
            print("-> posted comment to PR")

    return 0  # advisory: never fail the build


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
