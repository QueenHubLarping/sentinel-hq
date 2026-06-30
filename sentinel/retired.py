"""Durable `forget` backstop — the `.sentinel/retired.json` skip-list.

When `/sentinel intentional` retires a PR-keyed decision (via ``cognee.forget``), we
also record it here so a later re-ingest skips that decision even if Cognee's persistent
stores are rebuilt on an ephemeral CI runner. This REPLACES the old durability trick of
rewriting the ADR's `**Status:**` to `Superseded` in `docs/adr/` — there are no ADR files
and no `memory/` directory anymore (both deliberately killed). Memory lives in Cognee;
this tiny, non-user-facing ledger is only the re-ingest skip backstop.

The ledger is a small JSON list at the repo/workspace root:
  - `$SENTINEL_RETIRED_DIR/.sentinel/retired.json` (explicit override), else
  - `$GITHUB_WORKSPACE/.sentinel/retired.json`     (the consuming repo, in CI), else
  - `<sentinel-hq>/.sentinel/retired.json`          (local dev / tests).

In CI the file is committed back to the PR branch (see scripts/action_entrypoint.py) so
the retirement survives the next runner with no graph persistence required.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def sentinel_dir() -> Path:
    """The `.sentinel/` directory that holds Sentinel's durable backstops."""
    base = (
        os.environ.get("SENTINEL_RETIRED_DIR")
        or os.environ.get("GITHUB_WORKSPACE")
        or str(_REPO_ROOT)
    )
    return Path(base) / ".sentinel"


def retired_ledger_path() -> Path:
    return sentinel_dir() / "retired.json"


def _load() -> list[dict]:
    path = retired_ledger_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001 — a corrupt ledger must never break ingest/forget
        return []


def record_retired(
    decision_reference: str,
    *,
    pr_number: int | None = None,
    data_ids: list[str] | None = None,
) -> Path:
    """Append a retired decision to the ledger (idempotent on pr_number + reference).

    Returns the ledger path (so the caller can git-commit it on a CI runner).
    """
    entries = _load()
    # Idempotent per decision: dedup on the PR number when present (a PR is one decision),
    # else on the reference text.
    if pr_number is not None:
        already = any(e.get("pr_number") == pr_number for e in entries)
    else:
        already = any(e.get("decision_reference") == decision_reference for e in entries)
    if not already:
        entries.append({
            "decision_reference": decision_reference,
            "pr_number": pr_number,
            "data_ids": list(data_ids or []),
            "retired_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        path = retired_ledger_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    return retired_ledger_path()


def retired_pr_numbers() -> set[int]:
    """PR numbers whose decision has been retired (skip these on re-ingest)."""
    out: set[int] = set()
    for e in _load():
        n = e.get("pr_number")
        if n is not None:
            try:
                out.add(int(n))
            except (TypeError, ValueError):
                pass
    return out


def retired_data_ids() -> set[str]:
    """Stable data_ids that have been retired (skip these on re-ingest)."""
    out: set[str] = set()
    for e in _load():
        for d in e.get("data_ids") or []:
            out.add(str(d))
    return out
