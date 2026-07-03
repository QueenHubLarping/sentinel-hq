"""Stress-test Sentinel against the full corpus and report a precision table.

Runs the real detection loop (recall → judge) over EVERY incoming PR in the snapshot —
the reversal PRs Sentinel must catch AND the noise/control PRs it must stay silent on —
then prints and writes the honest number the demo needs (PRODUCT_SPEC §12.5):

    "N PRs, M flags, K correct."

Ground truth comes from the snapshot slugs: `noise_*` → must stay SILENT; anything else
is a reversal whose flag must cite the right decision (checked by keyword against the
establishing decision's vocabulary, so it survives renumbering by the seed script).

Usage:
    python scripts/stress_test.py            # reuse the existing graph (ingest if empty)
    python scripts/stress_test.py --wipe     # wipe stores + fresh ingest first
    python scripts/stress_test.py --recaps   # also write a Visual Memory Recap per catch

Report: STRESS_REPORT.md at the repo root.
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from sentinel.connection import setup_cognee  # noqa: E402  (must precede cognee import)
import cognee  # noqa: E402
from sentinel.detect import detect_reversal  # noqa: E402
from sentinel.ingest import ingest_corpus  # noqa: E402
from sentinel.sources import load_snapshot  # noqa: E402

# slug → keywords, ANY of which must appear in the verdict's decision reference/reasoning
# for the citation to count as correct. Keyword-based (not PR numbers) so the ground truth
# survives the seed script renumbering everything in a real repo.
EXPECTED_DECISION_WORDS = {
    "sync_email": ("email", "async", "queue", "celery"),
    "app_ratelimit": ("rate", "limit", "gateway", "nginx"),
    "app_ratelimit_orders": ("rate", "limit", "gateway", "nginx"),
    "db_sessions": ("token", "session", "auth", "stateless"),
    "drop_idempotency": ("idempoten", "capture", "payment"),
    "direct_db": ("pgbouncer", "pool", "postgres"),
    "join_search": ("search", "read", "denormal"),
    "inline_webhooks": ("webhook", "callback", "queue", "ack"),
}


async def _node_count() -> int:
    from cognee.infrastructure.databases.graph import get_graph_engine

    nodes, _ = await (await get_graph_engine()).get_graph_data()
    return len(nodes)


def _citation_ok(slug: str, verdict) -> bool:
    hay = f"{verdict.decision_reference} {verdict.original_reasoning} {verdict.evidence_chain}".lower()
    return any(w in hay for w in EXPECTED_DECISION_WORDS.get(slug, ()))


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wipe", action="store_true", help="wipe Cognee stores + fresh ingest")
    parser.add_argument("--recaps", action="store_true", help="write a Visual Memory Recap per catch")
    args = parser.parse_args()

    if args.wipe:
        from scripts.wipe import main as wipe_main  # local debug helper

        await wipe_main()

    await setup_cognee()
    if await _node_count() == 0:
        print("-> graph empty; ingesting full corpus...")
        await ingest_corpus()
    print(f"-> graph ready: {await _node_count()} nodes\n")

    snap = load_snapshot() or {}
    incoming = snap.get("incoming", []) or []
    if not incoming:
        print("No incoming PRs in the snapshot — nothing to test.")
        return 1

    rows = []
    t_total = time.time()
    for pr in incoming:
        slug = pr.get("slug") or str(pr.get("number"))
        expect_silent = slug.startswith("noise_")
        t0 = time.time()
        verdict = await detect_reversal(pr.get("text", ""))
        dt = time.time() - t0

        flagged = verdict.should_flag
        if expect_silent:
            outcome = "OK (silent)" if not flagged else "FALSE POSITIVE"
        elif not flagged:
            outcome = "FALSE NEGATIVE"
        else:
            outcome = "OK (caught)" if _citation_ok(slug, verdict) else "CAUGHT, WRONG CITATION"

        rows.append({
            "pr": pr.get("number"), "slug": slug,
            "expected": "silent" if expect_silent else "flag",
            "flagged": flagged, "confidence": verdict.confidence,
            "tier": verdict.provenance_tier if flagged else "",
            "reference": verdict.decision_reference if flagged else "",
            "outcome": outcome, "seconds": dt,
        })
        print(f"  PR #{pr.get('number'):>3} {slug:22} expected={'silent' if expect_silent else 'flag  '} "
              f"→ {'FLAG ' + f'{verdict.confidence:.0%}' if flagged else 'silent'}  [{outcome}] ({dt:.0f}s)")

        if args.recaps and flagged:
            from sentinel.recap import recap_from_live_graph

            html = await recap_from_live_graph(verdict, pr.get("text", ""))
            if html:
                out = _REPO_ROOT / f"recap_{slug}.html"
                out.write_text(html, encoding="utf-8")
                print(f"        recap → {out.name}")

    # ---- the honest numbers ------------------------------------------------
    reversals = [r for r in rows if r["expected"] == "flag"]
    noise = [r for r in rows if r["expected"] == "silent"]
    caught = [r for r in reversals if r["flagged"]]
    correct = [r for r in reversals if r["outcome"] == "OK (caught)"]
    fp = [r for r in noise if r["flagged"]]
    flags = [r for r in rows if r["flagged"]]

    print(f"\n{'=' * 68}")
    print(f"  {len(rows)} PRs reviewed → {len(flags)} flags")
    print(f"  reversals caught     : {len(caught)}/{len(reversals)} "
          f"(correct citation {len(correct)}/{len(caught) or 1})")
    print(f"  noise stayed silent  : {len(noise) - len(fp)}/{len(noise)}")
    if flags:
        print(f"  precision (flags that were real reversals): {len(caught)}/{len(flags)} "
              f"= {len(caught) / len(flags):.0%}")
    print(f"  total wall time      : {time.time() - t_total:.0f}s")

    # ---- report ------------------------------------------------------------
    lines = [
        "# Sentinel stress-test report",
        "",
        f"_{len(rows)} incoming PRs ({len(reversals)} reversals + {len(noise)} noise controls) "
        f"reviewed against a graph of {await _node_count()} nodes built from "
        f"{len(snap.get('prs', []))} merged PRs + {len(snap.get('issues', []))} incident issues._",
        "",
        "| PR | slug | expected | result | confidence | tier | cited decision | outcome |",
        "|---:|------|----------|--------|-----------:|------|----------------|---------|",
    ]
    for r in rows:
        lines.append(
            f"| #{r['pr']} | {r['slug']} | {r['expected']} | "
            f"{'flag' if r['flagged'] else 'silent'} | "
            f"{f'{r['confidence']:.0%}' if r['flagged'] else '—'} | {r['tier'] or '—'} | "
            f"{(r['reference'] or '—')[:48]} | {r['outcome']} |"
        )
    lines += [
        "",
        f"**{len(rows)} PRs, {len(flags)} flags, {len(caught)} genuine reversals caught "
        f"({len(correct)} with correct citations); {len(noise) - len(fp)}/{len(noise)} "
        f"noise PRs correctly silent.**",
    ]
    report = _REPO_ROOT / "STRESS_REPORT.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nreport → {report}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
