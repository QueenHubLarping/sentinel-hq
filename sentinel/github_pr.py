"""
PR input/output for the GitHub Action. Dry-run by default (no token, no network).

- load_pr_text: from a local markdown file (testing) or the GitHub event payload.
- post_comment: post to the PR via the GitHub API (only used in mode=post).
"""

import json
import os
import urllib.request
from pathlib import Path


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
    """Post a comment to the current PR. Requires GITHUB_TOKEN + GitHub event context."""
    token = os.environ["GITHUB_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    pr_number = event["pull_request"]["number"]

    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    req = urllib.request.Request(
        url,
        data=json.dumps({"body": comment}).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "sentinel-bot",
        },
    )
    urllib.request.urlopen(req)
