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

import os
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
