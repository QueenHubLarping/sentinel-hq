#!/usr/bin/env python3
"""Seed a real GitHub repo with Sentinel's demo data, then regenerate the snapshot.

The data is "born in GitHub": there is no markdown corpus. This script creates, via the
GitHub REST API, the exact content recorded in ``.sentinel/api_snapshot.json``:

  * 3 incident **issues** (#27/#58/#91 in the source content) — where the "why" lives.
  * 3 merged establishing-decision **PRs** (#19 gateway rate-limit, #31 Postgres,
    #42 async email) — each with a real file change so it has a diff, then merged.
  * 3 OPEN reversal **PRs** (the ``incoming`` array) — the changes Sentinel reviews.

After seeding, it re-reads the LIVE repo (``sources.fetch_merged_prs`` /
``fetch_issues``) and rewrites the snapshot so offline replay reflects real API
responses, then writes ``.sentinel/approved.json`` (the merged establishing-PR numbers,
so the trust tier marks those decisions human-approved → confident flags).

LIVE mode requires both:
    SENTINEL_SEED_REPO=owner/name   (target repo to seed)
    GITHUB_TOKEN=<repo-scope PAT>   (create issues/PRs, push branches, merge)

Without both — or with --dry-run — the script makes NO API calls: it prints the plan
from the snapshot, so it is always safe to invoke for a self-check.
"""

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
from pathlib import Path

# Make the `sentinel` package importable when run as `python scripts/seed_demo_repo.py`.
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from sentinel.github_pr import _api  # noqa: E402  (reuse the one authenticated HTTP helper)
from sentinel import sources  # noqa: E402
from sentinel.retired import sentinel_dir  # noqa: E402


# ---------------------------------------------------------------------------
# Small helpers (pure / planning) — no network
# ---------------------------------------------------------------------------

def _theme(text: str) -> str:
    """Classify a PR title/body into a decision theme, so reversals can be matched to
    the establishing decision they overturn without hard-coding PR numbers."""
    t = (text or "").lower()
    if "email" in t:
        return "email"
    if "throttle" in t or "ratelimit" in t or "rate limit" in t or "rate-limit" in t:
        return "ratelimit"
    if "session" in t or "signed token" in t or "revocation" in t:
        return "auth"
    if "idempotency" in t or "dedupe bookkeeping" in t or "capture" in t:
        return "payments_capture"
    if "pgbouncer" in t or "pooling" in t or "straight to the database" in t:
        return "db_pooling"
    if "search" in t or "read table" in t:
        return "search"
    if "webhook" in t or "callback" in t:
        return "webhooks"
    if "postgres" in t or "mongo" in t or "sql" in t:
        return "datastore"
    return "other"


def _pick_real_path(files: list[str]) -> str | None:
    """Pick a plausible real file path from a PR's ``files`` array for the Contents API.

    The snapshot's ``files`` arrays mix true paths with route fragments ("/search",
    "/api/") and dir markers ("tests/"); we want a concrete file with an extension.
    """
    for f in files or []:
        f = (f or "").strip()
        if not f or f.startswith("/") or f.endswith("/"):
            continue
        if "." in Path(f).name:
            return f
    return None


def _first_issue_ref(body: str) -> int | None:
    """The first ``issue #N`` referenced in a PR body (its linked incident)."""
    m = re.search(r"issue\s+#(\d+)", body or "", flags=re.IGNORECASE)
    return int(m.group(1)) if m else None


def _rewrite_issue_refs(text: str, remap: dict[int, int]) -> str:
    """Rewrite ``issue #<old>`` references to the real created issue numbers."""
    def repl(m: re.Match) -> str:
        old = int(m.group(2))
        return f"{m.group(1)}{remap.get(old, old)}"

    return re.sub(r"(issue\s+#)(\d+)", repl, text or "", flags=re.IGNORECASE)


def _establishing_stub(pr: dict, path: str) -> str:
    """A short stub-file body so the establishing PR carries a real diff."""
    return (
        "# Seed stub created by scripts/seed_demo_repo.py\n"
        f"# Establishing-decision PR: {pr.get('title', '').strip()}\n"
        f"# Touches: {path}\n"
        "# The real rationale ('why') lives in the linked incident issue, not this diff.\n"
    )


# ---------------------------------------------------------------------------
# API call wrapper — prints the error body, tolerates known-benign statuses
# ---------------------------------------------------------------------------

def _safe_api(path: str, method: str = "GET", body: dict | None = None,
              ok_statuses: tuple[int, ...] = (), label: str = ""):
    """Call ``_api`` and return (data, error_code).

    ``ok_statuses`` are treated as benign (e.g. 422 = branch/PR already exists, 404 =
    file not present): returns (None, code) instead of raising. Any other HTTP error
    prints the response body and re-raises.
    """
    try:
        return _api(path, method=method, body=body), None
    except urllib.error.HTTPError as e:  # noqa: PERF203
        raw = ""
        try:
            raw = e.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            pass
        if e.code in ok_statuses:
            return None, e.code
        tag = f" ({label})" if label else ""
        print(f"   ! API error {e.code} on {method} {path}{tag}: {raw}")
        raise


# ---------------------------------------------------------------------------
# Live GitHub operations
# ---------------------------------------------------------------------------

def _default_branch_and_sha(repo: str) -> tuple[str, str]:
    info, _ = _safe_api(f"/repos/{repo}", label="get repo")
    default = info["default_branch"]
    ref, _ = _safe_api(f"/repos/{repo}/git/ref/heads/{default}", label="get default ref")
    return default, ref["object"]["sha"]


def _create_branch(repo: str, branch: str, sha: str) -> None:
    _, err = _safe_api(
        f"/repos/{repo}/git/refs", method="POST",
        body={"ref": f"refs/heads/{branch}", "sha": sha},
        ok_statuses=(422,), label="create branch",
    )
    if err == 422:
        print(f"   branch {branch} already exists — reusing")


def _put_file(repo: str, path: str, branch: str, content: str, message: str) -> None:
    # An update needs the existing blob sha; a create must omit it.
    existing, _ = _safe_api(
        f"/repos/{repo}/contents/{path}?ref={branch}", ok_statuses=(404,), label="get file",
    )
    body = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": branch,
    }
    if isinstance(existing, dict) and existing.get("sha"):
        body["sha"] = existing["sha"]
    _safe_api(f"/repos/{repo}/contents/{path}", method="PUT", body=body, label="put file")


def _open_pr(repo: str, title: str, body: str, head: str, base: str) -> int:
    pr, err = _safe_api(
        f"/repos/{repo}/pulls", method="POST",
        body={"title": title, "body": body, "head": head, "base": base},
        ok_statuses=(422,), label="open PR",
    )
    if err == 422:
        owner = repo.split("/")[0]
        existing, _ = _safe_api(
            f"/repos/{repo}/pulls?state=all&head={owner}:{head}", label="find existing PR",
        )
        if existing:
            num = existing[0]["number"]
            print(f"   PR for {head} already exists (#{num}) — reusing")
            return num
        raise SystemExit(f"open PR failed for head {head} and no existing PR found")
    return pr["number"]


def _merge_pr(repo: str, number: int) -> None:
    for attempt in range(3):
        res, err = _safe_api(
            f"/repos/{repo}/pulls/{number}/merge", method="PUT",
            body={"merge_method": "merge"},
            ok_statuses=(405, 409), label="merge PR",
        )
        if err is None:
            print(f"   merged PR #{number}")
            return
        # 405/409: not yet mergeable (GitHub still computing) or already merged.
        meta, _ = _safe_api(f"/repos/{repo}/pulls/{number}", label="check PR merged")
        if isinstance(meta, dict) and meta.get("merged"):
            print(f"   PR #{number} already merged — continuing")
            return
        if attempt < 2:
            time.sleep(2)
    print(f"   ! could not merge PR #{number} (left open); re-run to retry")


# ---------------------------------------------------------------------------
# Planning (shared by dry-run and live so output is consistent)
# ---------------------------------------------------------------------------

def _plan(snap: dict) -> dict:
    """Build the create-plan from the snapshot content (no network)."""
    issues = snap.get("issues", []) or []
    prs = snap.get("prs", []) or []
    incoming = snap.get("incoming", []) or []

    est = []
    for pr in prs:
        path = _pick_real_path(pr.get("files", [])) or f"sentinel_seed/decision_{pr['number']}.py"
        est.append({
            "orig_number": pr["number"],
            "title": pr.get("title", ""),
            "body": pr.get("body", ""),
            "branch": f"sentinel-seed-pr-{pr['number']}",
            "path": path,
            "incident_orig": _first_issue_ref(pr.get("body", "")),
            "theme": _theme(f"{pr.get('title','')} {pr.get('body','')}"),
        })

    rev = []
    for pr in incoming:
        rev.append({
            "orig_number": pr["number"],
            "slug": pr.get("slug", ""),
            "title": pr.get("title", ""),
            "text": pr.get("text", ""),
            "branch": f"sentinel-seed-reversal-{pr['number']}",
            "path": f"sentinel_seed/reversal_{pr.get('slug') or pr['number']}.md",
            "theme": _theme(f"{pr.get('title','')} {pr.get('text','')}"),
        })

    return {"issues": issues, "establishing": est, "reversal": rev}


def _print_plan(plan: dict) -> None:
    print("\n=== PLANNED ISSUES (incidents — the 'why') ===")
    for it in plan["issues"]:
        labels = ", ".join(it.get("labels", []) or [])
        print(f"  issue #{it['number']} [{labels}]  {it['title']}")

    print("\n=== PLANNED ESTABLISHING PRs (merged decisions) ===")
    for e in plan["establishing"]:
        print(f"  PR #{e['orig_number']} ({e['theme']})  {e['title']}")
        print(f"      branch={e['branch']}  file={e['path']}  links→issue #{e['incident_orig']}")

    print("\n=== PLANNED REVERSAL PRs (open — Sentinel reviews these) ===")
    for r in plan["reversal"]:
        print(f"  PR #{r['orig_number']} ({r['theme']}, slug={r['slug']})  {r['title']}")
        print(f"      branch={r['branch']}  file={r['path']}")


def _print_mapping(plan: dict, issue_map: dict[int, int], pr_map: dict[int, int],
                   rev_map: dict[int, int]) -> None:
    """Print decision → (issue #, decision PR #, reversal PR #).

    *_map dicts translate the snapshot's original numbers to the real created numbers;
    in dry-run they are identity maps so the planned (source) numbers are shown.
    """
    # Index reversals by theme so each decision can list the PR that overturns it.
    rev_by_theme: dict[str, list[dict]] = {}
    for r in plan["reversal"]:
        rev_by_theme.setdefault(r["theme"], []).append(r)

    print("\n=== DECISION MAPPING (issue # → decision PR # → reversal PR #) ===")
    for e in plan["establishing"]:
        issue_no = issue_map.get(e["incident_orig"], e["incident_orig"])
        dec_no = pr_map.get(e["orig_number"], e["orig_number"])
        reversals = rev_by_theme.get(e["theme"], [])
        rev_str = ", ".join(
            f"#{rev_map.get(r['orig_number'], r['orig_number'])} ({r['slug']})"
            for r in reversals
        ) or "(none)"
        print(f"  {e['title']}")
        print(f"      incident issue #{issue_no}  →  decision PR #{dec_no}  →  reversal PR(s): {rev_str}")


# ---------------------------------------------------------------------------
# Snapshot regeneration + approved.json
# ---------------------------------------------------------------------------

def _regenerate_snapshot(repo: str, orig_incoming: list[dict]) -> Path:
    """Re-read the live repo and rewrite the snapshot (prs + issues + incoming)."""
    prs = sources.fetch_merged_prs()
    issues = sources.fetch_issues()
    path = sources.save_snapshot(prs, issues, repo)

    # save_snapshot only writes prs+issues; preserve the `incoming` array by fetching the
    # live OPEN PRs and mapping each back to its original slug by title.
    slug_by_title = {pr.get("title", ""): pr.get("slug", "") for pr in orig_incoming}
    open_prs, _ = _safe_api(f"/repos/{repo}/pulls?state=open&per_page=100", label="list open PRs")
    incoming = []
    for pr in open_prs or []:
        title = pr.get("title", "") or ""
        incoming.append({
            "number": pr["number"],
            "slug": slug_by_title.get(title, ""),
            "title": title,
            "state": pr.get("state", "open") or "open",
            "text": pr.get("body") or "",
        })

    data = json.loads(path.read_text(encoding="utf-8"))
    data["_note"] = (
        "API-sourced snapshot (offline replay). Regenerated by scripts/seed_demo_repo.py."
    )
    data["incoming"] = incoming
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def _write_approved(pr_numbers: list[int]) -> Path:
    path = sentinel_dir() / "approved.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(set(pr_numbers)), indent=2) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_live(repo: str, plan: dict, orig_incoming: list[dict]) -> None:
    os.environ["GITHUB_REPOSITORY"] = repo  # the _api helper + sources read this

    default_branch, _ = _default_branch_and_sha(repo)
    print(f"\nSeeding {repo} (default branch: {default_branch})")

    # 1) Issues -------------------------------------------------------------
    print("\n[1/5] Creating incident issues...")
    issue_map: dict[int, int] = {}
    for it in plan["issues"]:
        created, _ = _safe_api(
            f"/repos/{repo}/issues", method="POST",
            body={
                "title": it.get("title", ""),
                "body": it.get("body", ""),
                "labels": it.get("labels", []) or [],
            },
            label="create issue",
        )
        issue_map[it["number"]] = created["number"]
        print(f"   issue #{created['number']}  {it.get('title','')}")

    # 2) Establishing PRs (created, then merged) ---------------------------
    print("\n[2/5] Creating + merging establishing-decision PRs...")
    pr_map: dict[int, int] = {}
    merged_numbers: list[int] = []
    for e in plan["establishing"]:
        _, head_sha = _default_branch_and_sha(repo)  # re-read: prior merges moved HEAD
        _create_branch(repo, e["branch"], head_sha)
        body = _rewrite_issue_refs(e["body"], issue_map)
        _put_file(repo, e["path"], e["branch"], _establishing_stub(e, e["path"]),
                  f"seed: {e['title']}")
        num = _open_pr(repo, e["title"], body, e["branch"], default_branch)
        pr_map[e["orig_number"]] = num
        print(f"   opened PR #{num}  {e['title']}")
        _merge_pr(repo, num)
        merged_numbers.append(num)

    # 3) Reversal PRs (left OPEN) ------------------------------------------
    print("\n[3/5] Creating open reversal PRs (NOT merged)...")
    rev_map: dict[int, int] = {}
    for r in plan["reversal"]:
        _, head_sha = _default_branch_and_sha(repo)
        _create_branch(repo, r["branch"], head_sha)
        _put_file(repo, r["path"], r["branch"], r["text"] + "\n",
                  f"reversal: {r['title']}")
        num = _open_pr(repo, r["title"], r["text"], r["branch"], default_branch)
        rev_map[r["orig_number"]] = num
        print(f"   opened reversal PR #{num} ({r['slug']})  {r['title']}")

    # 4) Regenerate snapshot from the live repo ----------------------------
    print("\n[4/5] Regenerating snapshot from the live repo...")
    snap_path = _regenerate_snapshot(repo, orig_incoming)
    print(f"   wrote {snap_path}")

    # 5) approved.json = the real merged establishing-PR numbers -----------
    print("\n[5/5] Writing approved.json (human-ratified decisions)...")
    approved_path = _write_approved(merged_numbers)
    print(f"   wrote {approved_path}: {sorted(set(merged_numbers))}")

    _print_mapping(plan, issue_map, pr_map, rev_map)
    print("\nDone. The snapshot now replays real GitHub API responses.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print the plan and make NO API calls (default when creds are missing).",
    )
    parser.add_argument(
        "--repo", default=os.environ.get("SENTINEL_SEED_REPO"),
        help="Target repo 'owner/name' (or set SENTINEL_SEED_REPO).",
    )
    args = parser.parse_args()

    repo = args.repo
    token = os.environ.get("GITHUB_TOKEN")
    have_creds = bool(repo and token)
    dry_run = args.dry_run or not have_creds

    snap = sources.load_snapshot()
    if not snap:
        raise SystemExit(f"No source snapshot found at {sources.snapshot_path()} — cannot plan.")
    plan = _plan(snap)

    print("Sentinel demo seed")
    print(f"  target repo : {repo or '(unset — set SENTINEL_SEED_REPO)'}")
    print(f"  token       : {'present' if token else 'MISSING'}")
    print(f"  mode        : {'DRY-RUN (no API calls)' if dry_run else 'LIVE'}")

    _print_plan(plan)

    if dry_run:
        ident = {it["number"]: it["number"] for it in plan["issues"]}
        ipr = {e["orig_number"]: e["orig_number"] for e in plan["establishing"]}
        irev = {r["orig_number"]: r["orig_number"] for r in plan["reversal"]}
        _print_mapping(plan, ident, ipr, irev)
        if not have_creds:
            print("\n[dry-run] Set SENTINEL_SEED_REPO + GITHUB_TOKEN (repo scope) to run live.")
        else:
            print("\n[dry-run] Re-run without --dry-run to create this in GitHub.")
        return

    run_live(repo, plan, snap.get("incoming", []) or [])


if __name__ == "__main__":
    main()
