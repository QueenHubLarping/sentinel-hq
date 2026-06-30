"""
PR input/output for the GitHub Action. Dry-run by default (no token, no network).

- load_pr_text: from a local markdown file (testing) or the GitHub event payload.
- post_comment: post to the PR via the GitHub API (only used in mode=post).

Resolve helpers (used by the '/sentinel intentional' issue_comment flow):
- load_event / event_name / issue_number / comment_body — read the event payload.
- find_flagged_decision_text — locate Sentinel's prior reversal comment on the PR.
- pr_head_branch — the PR's source branch (so we can commit the supersession there).
- commit_and_push — record the ADR status change back to the PR branch.
"""

import json
import os
import subprocess
import urllib.request
from pathlib import Path


def _api(path: str, method: str = "GET", body: dict | None = None):
    """Minimal authenticated GitHub REST call. Requires GITHUB_TOKEN + GITHUB_REPOSITORY."""
    token = os.environ["GITHUB_TOKEN"]
    url = f"https://api.github.com{path}"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "sentinel-bot",
        },
    )
    with urllib.request.urlopen(req) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else None


def load_event() -> dict:
    """The GitHub Actions event payload (empty dict when not running in CI)."""
    p = os.environ.get("GITHUB_EVENT_PATH")
    if p and Path(p).exists():
        return json.loads(Path(p).read_text(encoding="utf-8"))
    return {}


def event_name() -> str:
    return os.environ.get("GITHUB_EVENT_NAME", "")


def comment_body() -> str:
    """The triggering comment's body (issue_comment events)."""
    return (load_event().get("comment", {}) or {}).get("body", "") or ""


def issue_number() -> int | None:
    """PR/issue number, for both pull_request and issue_comment events."""
    ev = load_event()
    if "issue" in ev:
        return ev["issue"].get("number")
    if "pull_request" in ev:
        return ev["pull_request"].get("number")
    return None


def pr_head_branch(number: int) -> str:
    """The PR's source (head) branch name — where the supersession is committed."""
    repo = os.environ["GITHUB_REPOSITORY"]
    return _api(f"/repos/{repo}/pulls/{number}")["head"]["ref"]


def find_flagged_decision_text(number: int) -> str:
    """Return the body of Sentinel's most recent reversal comment on this PR, or ''.

    We read the decision reference (e.g. 'ADR-001') straight from the comment Sentinel
    already posted — no need to re-run detection just to identify the ADR.
    """
    repo = os.environ["GITHUB_REPOSITORY"]
    comments = _api(f"/repos/{repo}/issues/{number}/comments?per_page=100") or []
    for c in reversed(comments):
        body = c.get("body", "")
        # The reliable marker across every Sentinel flag card (the Memory Review card and the
        # legacy reversal card both carry the CTA); also matches old "reverses a past" headlines.
        if "/sentinel intentional" in body or "Memory Review" in body or "reverses a past" in body:
            return body
    return ""


def checkout_branch(branch: str) -> None:
    """Fetch and check out *branch* in the workspace (issue_comment starts on default)."""
    workspace = os.environ.get("GITHUB_WORKSPACE", ".")
    subprocess.run(["git", "fetch", "origin", branch], cwd=workspace, check=True)
    subprocess.run(["git", "checkout", "-B", branch, "FETCH_HEAD"], cwd=workspace, check=True)


def commit_and_push(branch: str, message: str) -> bool:
    """Commit all working-tree changes and push to *branch* (uses checkout's token).

    Idempotent: if nothing changed (e.g. the ADR was already superseded by an earlier
    '/sentinel intentional'), it does nothing and returns False instead of failing on an
    empty commit. Returns True when a commit was pushed.
    """
    workspace = os.environ.get("GITHUB_WORKSPACE", ".")
    run = lambda *a: subprocess.run(a, cwd=workspace, check=True)
    run("git", "config", "user.name", "sentinel-bot")
    run("git", "config", "user.email", "sentinel-bot@users.noreply.github.com")
    run("git", "add", "-A")
    # `git diff --cached --quiet` exits non-zero iff there are staged changes.
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=workspace).returncode == 0:
        print("   (nothing to commit — ADR already superseded)")
        return False
    run("git", "commit", "-m", message)
    run("git", "push", "origin", f"HEAD:{branch}")
    return True


def load_pr_text(pr_file: str | None = None) -> str:
    """Return the PR text. Prefer an explicit file (local/testing); otherwise read the
    PR title+body from the GitHub Actions event payload."""
    if pr_file:
        return Path(pr_file).read_text(encoding="utf-8")

    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if event_path and Path(event_path).exists():
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
        pr = event.get("pull_request", {})
        title = pr.get("title", "")
        body = pr.get("body") or ""
        return f"# {title}\n\n{body}"

    raise SystemExit("No PR source: pass a file path or run inside a GitHub PR event.")


def post_comment(comment: str) -> None:
    """Post a comment to the current PR. Works for both pull_request and issue_comment
    events (issue_number handles both shapes). Requires GITHUB_TOKEN + event context."""
    repo = os.environ["GITHUB_REPOSITORY"]
    number = issue_number()
    if number is None:
        raise SystemExit("post_comment: could not determine the PR/issue number from the event.")
    _api(f"/repos/{repo}/issues/{number}/comments", method="POST", body={"body": comment})
