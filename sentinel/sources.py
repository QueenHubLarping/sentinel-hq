"""
Sentinel memory sources — build the decision corpus from a repo's REAL history.

A real deployment ships no seeded markdown: institutional memory already lives in the
team's GitHub history and in-repo docs. Sentinel gathers it at `remember` time:

  - repo docs   : decision docs already in the checkout (ADRs, docs/**, design notes)
  - merged PRs  : the team's actual "why" — title, body, author, merge date, changed
                  files — via the GitHub REST API (the repo the Action already runs in)
  - connectors  : *attached* exports (Slack / Linear / Notion) when a path is configured

Everything is self-hosted into Cognee; the only remote reads are the GitHub API calls
for this repo's own PRs. When run OUTSIDE a GitHub Action (local dev / tests), callers
fall back to the bundled demo corpus — see ingest.ingest_corpus.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sentinel.github_pr import _api

# Default places a repo keeps decision docs (targeted, to avoid ingesting noise like
# READMEs). Override/broaden with SENTINEL_DOC_GLOBS (comma-separated, relative to the
# repo root / $GITHUB_WORKSPACE) — e.g. add "docs/**/*.md" for a docs-heavy repo.
_DEFAULT_DOC_GLOBS = "docs/adr/*.md,docs/decisions/*.md,docs/rfcs/*.md,ADR-*.md"


def repo_slug() -> str | None:
    """The 'owner/name' of the repo the Action runs in, or None outside CI."""
    return os.environ.get("GITHUB_REPOSITORY")


def in_github_action() -> bool:
    """True when we can read this repo's real history (repo + token present)."""
    return bool(repo_slug() and os.environ.get("GITHUB_TOKEN"))


def has_api_creds() -> bool:
    """True when a repo + token are configured, so we can hit the GitHub API."""
    return bool(repo_slug() and os.environ.get("GITHUB_TOKEN"))


# ---------------------------------------------------------------------------
# JSON snapshot — the offline-safe replay of API responses (no markdown corpus)
# ---------------------------------------------------------------------------
# Everything Sentinel remembers comes from the GitHub API. To keep the live demo off the
# network (PRODUCT_SPEC §13: never depend on the network on stage) we cache the raw API
# responses to a JSON snapshot and replay from it. It is still 100% API-sourced data —
# just recorded. The seed script (scripts/seed_demo_repo.py) writes it after creating the
# demo PRs/issues; `gather_memory` reads it when there are no live creds.

_USED_LIVE = False  # set by gather_memory so callers can report the source


def snapshot_path() -> Path:
    """Path to the cached API snapshot (override with SENTINEL_API_SNAPSHOT)."""
    override = os.environ.get("SENTINEL_API_SNAPSHOT")
    if override:
        return Path(override)
    from sentinel.retired import sentinel_dir

    return sentinel_dir() / "api_snapshot.json"


def load_snapshot() -> dict | None:
    """Load the cached snapshot ({'repo','generated_at','prs':[...],'issues':[...]}) or None."""
    path = snapshot_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001 — a corrupt snapshot must not break remember
        return None


def save_snapshot(prs: list[dict], issues: list[dict], repo: str | None = None) -> Path:
    """Write the API responses to the snapshot cache (the seed script / a refresh calls this)."""
    path = snapshot_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "repo": repo or repo_slug() or "",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "prs": prs,
        "issues": issues,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def refreshing_live() -> bool:
    """Whether the most recent gather_memory() read from the live API (vs. the snapshot)."""
    return _USED_LIVE


def incoming_prs() -> list[dict]:
    """Open PRs under review (the changes being evaluated), from the snapshot's `incoming`.

    These are NOT memory — they're the PRs Sentinel reviews against memory. Each entry has
    {number, slug, title, state, text}; `text` is the full PR text (description + diff) that
    detect.detect_reversal consumes. Empty if there's no snapshot.
    """
    snap = load_snapshot()
    return (snap.get("incoming", []) or []) if snap else []


def incoming_text(key) -> str:
    """The full text of an incoming PR by slug or number (for local detection/demo runs)."""
    for pr in incoming_prs():
        if str(pr.get("slug")) == str(key) or str(pr.get("number")) == str(key):
            return pr.get("text", "") or ""
    return ""


def gather_memory(limit: int = 25) -> tuple[list[dict], list[dict]]:
    """Return (pr_dicts, issue_dicts) for `remember` — from the live API or the snapshot.

    Precedence:
      1. live API, when creds exist AND (no snapshot yet OR SENTINEL_REFRESH_SNAPSHOT=true) —
         the fetched responses are written to the snapshot cache as a side effect.
      2. the cached JSON snapshot (the offline / demo default).
      3. ([], []) when neither is available — remember degrades gracefully.
    """
    global _USED_LIVE
    _USED_LIVE = False

    refresh = os.environ.get("SENTINEL_REFRESH_SNAPSHOT", "false").strip().lower() == "true"
    snap = load_snapshot()

    if has_api_creds() and (snap is None or refresh):
        try:
            prs = fetch_merged_prs(limit)
            issues = fetch_issues(limit)
            _USED_LIVE = True
            try:
                save_snapshot(prs, issues)
            except Exception:  # noqa: BLE001 — caching is best-effort
                pass
            return prs, issues
        except Exception:  # noqa: BLE001 — fall back to the snapshot on any API error
            pass

    if snap is not None:
        return snap.get("prs", []) or [], snap.get("issues", []) or []
    return [], []


# ---------------------------------------------------------------------------
# Merged pull requests — the real "why" behind past changes
# ---------------------------------------------------------------------------

def fetch_merged_prs(limit: int = 25, include_files: bool = True) -> list[dict]:
    """Return up to *limit* most-recently-updated MERGED PRs for the current repo.

    Each dict: {number, title, body, author, merged_at, files}. Network-bound; callers
    wrap this in try/except (remember must degrade gracefully if the API is unreachable).
    """
    repo = repo_slug()
    if not repo:
        return []
    out: list[dict] = []
    page = 1
    while len(out) < limit and page <= 6:
        batch = _api(
            f"/repos/{repo}/pulls?state=closed&sort=updated&direction=desc"
            f"&per_page=50&page={page}"
        ) or []
        if not batch:
            break
        for pr in batch:
            if not pr.get("merged_at"):
                continue  # closed-but-not-merged carries no decision
            files: list[str] = []
            if include_files:
                try:
                    fl = _api(f"/repos/{repo}/pulls/{pr['number']}/files?per_page=20") or []
                    files = [f["filename"] for f in fl]
                except Exception:
                    pass
            out.append({
                "number": pr["number"],
                "title": pr.get("title", "") or "",
                "body": pr.get("body") or "",
                "author": (pr.get("user") or {}).get("login", "") or "",
                "merged_at": pr.get("merged_at", "") or "",
                "files": files,
            })
            if len(out) >= limit:
                break
        page += 1
    return out


def pr_to_doc(pr: dict) -> tuple[str, str]:
    """Render a merged-PR dict into (label, tagged_markdown) for ingestion.

    PURE — no network. The tag header mirrors ingest._build_header so cognify extracts
    the same cross-document typed edges (author, files/component, pr_number) from a real
    PR as from a bundled corpus file.
    """
    num = pr.get("number")
    label = f"PR-{num}.md"
    parts = [f"[source_type: PR]", f"[file: {label}]", f"[pr_number: {num}]"]
    if pr.get("author"):
        parts.append(f"[author: {pr['author'].lstrip('@')}]")
    if pr.get("merged_at"):
        parts.append(f"[merged: {pr['merged_at'][:10]}]")
    header = " ".join(parts)
    if pr.get("files"):
        header += "\n[files: " + ", ".join(pr["files"][:12]) + "]"
    body = (pr.get("body") or "").strip() or "(no description provided)"
    content = f"{header}\n\n# PR #{num}: {pr.get('title', '').strip()}\n\n{body}\n"
    return label, content


# ---------------------------------------------------------------------------
# Linked issues — the rationale (the WHY) behind past decisions
# ---------------------------------------------------------------------------

def fetch_issues(limit: int = 25) -> list[dict]:
    """Return up to *limit* most-recently-updated issues for the current repo.

    The GitHub `issues` endpoint also returns pull requests — those are filtered out
    (they carry a `pull_request` key) so only genuine issues (incidents/discussions, where
    rationale lives) are ingested. Network-bound; callers wrap this in try/except.
    """
    repo = repo_slug()
    if not repo:
        return []
    out: list[dict] = []
    page = 1
    while len(out) < limit and page <= 6:
        batch = _api(
            f"/repos/{repo}/issues?state=all&sort=updated&direction=desc"
            f"&per_page=50&page={page}"
        ) or []
        if not batch:
            break
        for it in batch:
            if it.get("pull_request"):
                continue  # the issues endpoint also returns PRs — skip them
            out.append({
                "number": it["number"],
                "title": it.get("title", "") or "",
                "body": it.get("body") or "",
                "author": (it.get("user") or {}).get("login", "") or "",
                "state": it.get("state", "") or "",
                "created_at": it.get("created_at", "") or "",
                "labels": [
                    lb.get("name", "") for lb in (it.get("labels") or []) if isinstance(lb, dict)
                ],
            })
            if len(out) >= limit:
                break
        page += 1
    return out


def issue_to_doc(issue: dict) -> tuple[str, str]:
    """Render an issue dict into (label, tagged_markdown) for ingestion.

    PURE — no network. Mirrors pr_to_doc and ingest._build_header's Issue branch so a live
    incident issue produces the same typed tags (issue_number, author, status) as a bundled one.
    """
    num = issue.get("number")
    label = f"ISSUE-{num}.md"
    parts = ["[source_type: Issue]", f"[file: {label}]", f"[issue_number: {num}]"]
    if issue.get("author"):
        parts.append(f"[author: {issue['author'].lstrip('@')}]")
    if issue.get("state"):
        parts.append(f"[status: {issue['state']}]")
    if issue.get("created_at"):
        parts.append(f"[date: {issue['created_at'][:10]}]")
    header = " ".join(parts)
    if issue.get("labels"):
        header += "\n[labels: " + ", ".join(lb for lb in issue["labels"][:8] if lb) + "]"
    body = (issue.get("body") or "").strip() or "(no description provided)"
    content = f"{header}\n\n# Issue #{num}: {issue.get('title', '').strip()}\n\n{body}\n"
    return label, content


# ---------------------------------------------------------------------------
# In-repo decision docs + attached connector exports (on disk in the checkout)
# ---------------------------------------------------------------------------

def _workspace() -> Path | None:
    ws = os.environ.get("GITHUB_WORKSPACE")
    return Path(ws) if ws and Path(ws).is_dir() else None


def repo_decision_docs() -> list[tuple[Path, str]]:
    """(path, source_type) for decision docs already in the repo checkout.

    source_type is 'ADR' for anything under an adr/ path (so the rich ADR metadata
    parser applies), else 'Doc'. Deduplicated, stable order. Empty outside an Action.
    """
    ws = _workspace()
    if not ws:
        return []
    globs = (os.environ.get("SENTINEL_DOC_GLOBS") or _DEFAULT_DOC_GLOBS).split(",")
    seen: set[Path] = set()
    docs: list[tuple[Path, str]] = []
    for g in globs:
        g = g.strip()
        if not g:
            continue
        for p in sorted(ws.glob(g)):
            if not p.is_file() or p in seen:
                continue
            seen.add(p)
            source_type = "ADR" if "adr" in str(p.relative_to(ws)).lower() else "Doc"
            docs.append((p, source_type))
    return docs


def slack_export_paths() -> list[Path]:
    """Attached Slack-export files (markdown), if SENTINEL_SLACK_DIR points at a dir.

    This is the 'attach your Slack' connector: a team exports the relevant threads and
    points Sentinel at them. Live Slack OAuth is roadmap, not hackathon scope.
    """
    d = os.environ.get("SENTINEL_SLACK_DIR")
    if not d or not Path(d).is_dir():
        return []
    return sorted(Path(d).glob("*.md"))
