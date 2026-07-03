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
from sentinel.comment import (  # noqa: E402
    render_comment,
    render_feedback_recorded,
    render_resolution,
)
from sentinel.detect import detect_reversal  # noqa: E402
from sentinel.github_pr import (  # noqa: E402
    checkout_branch,
    comment_body,
    commit_and_push,
    event_name,
    find_flagged_decision_text,
    issue_number,
    load_pr_text,
    post_comment,
    repo_default_branch,
)
from sentinel.improve import record_noise, record_noise_file  # noqa: E402
from sentinel.ingest import ingest_corpus  # noqa: E402
from sentinel.resolve import decision_ref_from_text, mark_intentional  # noqa: E402


async def _node_count() -> int:
    from cognee.infrastructure.databases.graph import get_graph_engine

    nodes, _ = await (await get_graph_engine()).get_graph_data()
    return len(nodes)


def _run_url() -> str:
    """URL of the current workflow run (where the recap artifact lands), or "" locally."""
    server = os.environ.get("GITHUB_SERVER_URL", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    return f"{server}/{repo}/actions/runs/{run_id}" if server and repo and run_id else ""


def _write_summary(comment: str) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        Path(summary_path).write_text(comment, encoding="utf-8")


async def handle_resolve() -> int:
    """Handle a '/sentinel intentional' comment: retire the flagged decision (forget).

    PR-keyed, two transports, one verb. The REAL Cognee verb: ``cognee.forget(data_id=...)``
    via mark_intentional(), which surgically removes that PR-keyed decision's nodes/embeddings
    from the persistent graph so the very next detection no longer flags it, AND records the
    retirement in ``.sentinel/retired.json``. The DURABLE backstop: that ledger is committed
    to the PR branch, so on the next ephemeral runner (no graph persistence) the re-ingest
    skips the retired decision. (Replaces the old "mark the ADR Superseded in docs/adr" trick —
    no ADR files, no `memory/`.) Sentinel is advisory: every failure is swallowed with a
    warning — the command never breaks the build.
    """
    if "/sentinel intentional" not in comment_body().lower():
        print("Comment is not '/sentinel intentional'; nothing to do.")
        return 0

    number = issue_number()
    decision_ref = decision_ref_from_text(find_flagged_decision_text(number)) if number else ""
    if not decision_ref:
        print("No prior Sentinel reversal flag found on this PR; nothing to retire.")
        post_comment("🛡️ _Sentinel_: I couldn't find a reversal I'd flagged on this PR to retire.")
        return 0

    # Check out the DEFAULT branch so the retired.json ledger reaches every future
    # run's merge ref (a PR-branch commit would only protect this one PR). This is
    # what makes the forget durable on ephemeral runners with no graph persistence.
    branch = None
    try:
        branch = repo_default_branch()
        checkout_branch(branch)
    except Exception as exc:  # noqa: BLE001 — advisory: no branch → skip the ledger commit, still forget
        print(f"branch checkout skipped (ledger won't be committed): {exc}")

    # The real Cognee verb: forget the PR-keyed decision from the persistent graph + write
    # the retired.json ledger. Never fail the command.
    try:
        await setup_cognee()
        result = await mark_intentional(decision_ref)
        print(f"-> native cognee.forget: {result.get('status')} "
              f"({result.get('retired_items', 0)} item(s)) for {decision_ref}")
    except Exception as exc:  # noqa: BLE001 — advisory: a flaky forget must not break the command
        print(f"native forget skipped: {exc}")

    # Durable backstop: commit .sentinel/retired.json so the retirement survives a fresh runner.
    if branch:
        try:
            commit_and_push(
                branch,
                f"chore(sentinel): retire {decision_ref} — intentional override in #{number}",
            )
        except Exception as exc:  # noqa: BLE001 — advisory: commit failure must not break the command
            print(f"ledger commit skipped: {exc}")

    post_comment(render_resolution(decision_ref, number))
    return 0


async def handle_feedback() -> int:
    """Handle a '/sentinel noise' comment: record a 👎 so this drift stops surfacing (improve).

    Two transports, one verb. The DURABLE backstop: append the drift signature to a
    `.sentinel-dismissed` file committed to the PR branch (the next detection reads it live
    and suppresses the flag). The REAL Cognee verb, run best-effort alongside it:
    record_noise() does ``cognee.add`` + ``cognee.cognify`` + ``cognee.improve``, writing the
    👎 into the graph itself. Sentinel is advisory: a native-verb failure prints a warning and
    is swallowed — the maintainer command never breaks.
    """
    if "/sentinel noise" not in comment_body().lower():
        print("Comment is not '/sentinel noise'; nothing to do.")
        return 0

    number = issue_number()
    decision_ref = decision_ref_from_text(find_flagged_decision_text(number)) if number else ""
    if not decision_ref:
        print("No prior Sentinel reversal flag found on this PR; nothing to mark as noise.")
        post_comment("🛡️ _Sentinel_: I couldn't find a flag of mine on this PR to mark as noise.")
        return 0

    # Commit the dismissal to the DEFAULT branch: the whole point of a 👎 is that the
    # drift stops surfacing on FUTURE, unrelated PRs — whose merge refs only ever
    # include main, not the branch of the PR where the maintainer said "noise".
    branch = repo_default_branch()
    checkout_branch(branch)
    path = record_noise_file(decision_ref)
    commit_and_push(branch, f"chore(sentinel): dismiss {decision_ref} drift as noise (/sentinel noise in #{number})")
    print(f"-> dismissed {decision_ref} drift as noise: updated {path.name} on {branch}")

    # The real Cognee verb, best-effort: write the 👎 into the graph via cognee.add +
    # cognify + improve (the .sentinel-dismissed file above is the durability backstop).
    # cognify/improve are LLM/embedding-heavy and can be slow/flaky — never fail the command.
    try:
        await setup_cognee()
        result = await record_noise(decision_ref, pr_number=number)
        print(f"-> native cognee.improve: {result.get('status')} for {result.get('signature', decision_ref)}")
    except Exception as exc:  # noqa: BLE001 — advisory: a flaky improve must not break the command
        print(f"native improve skipped (durable dismissal already recorded): {exc}")

    post_comment(render_feedback_recorded(decision_ref, number))
    return 0


async def main() -> int:
    # '/sentinel ...' replies arrive as issue_comment events — handle the forget
    # (intentional) and improve (noise) loops here, before the detection path.
    if event_name() == "issue_comment":
        body = comment_body().lower()
        if "/sentinel intentional" in body:
            return await handle_resolve()
        if "/sentinel noise" in body:
            return await handle_feedback()
        print("Comment is not a Sentinel command; nothing to do.")
        return 0

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

    # Best-effort: render the flagged decision's real subgraph as an inline Mermaid diagram
    # so the PR comment SHOWS the typed multi-hop graph Sentinel traversed. Never blocks.
    graph_section = ""
    if verdict.should_flag:
        try:
            from sentinel.graph_viz import evidence_mermaid

            first_line = next((ln.strip("# ").strip() for ln in pr_text.splitlines() if ln.strip()), "This PR")
            graph_section = await evidence_mermaid(verdict.decision_reference, incoming_label=first_line[:34])
        except Exception as exc:  # noqa: BLE001 — advisory: the diagram is a bonus, not required
            print(f"graph diagram skipped: {exc}")

    # Best-effort: render the interactive Visual Memory Recap (annotated diff + belief
    # card + the traversable evidence graph) as a self-contained HTML artifact. The
    # workflow's upload-artifact step publishes it; the comment links the run. Never blocks.
    recap_note = ""
    if verdict.should_flag:
        try:
            from sentinel.recap import recap_from_live_graph, write_recap

            recap_html = await recap_from_live_graph(
                verdict, pr_text, repo=os.environ.get("GITHUB_REPOSITORY", "")
            )
            if recap_html:
                recap_path = write_recap(recap_html)
                print(f"-> visual memory recap written: {recap_path}")
                # Best of both: a LIVE GitHub Pages link (renders in the browser) with
                # the workflow-artifact link as the durable fallback.
                live_url = ""
                try:
                    from sentinel.github_pr import issue_number, publish_recap_page

                    number = issue_number()
                    if number and os.environ.get("GITHUB_TOKEN"):
                        live_url = publish_recap_page(recap_html, number)
                        print(f"-> recap published live: {live_url}")
                except Exception as exc:  # noqa: BLE001 — advisory: Pages publish is a bonus
                    print(f"recap live-publish skipped: {exc}")
                run_url = _run_url()
                if live_url:
                    recap_note = (
                        "\n\n<sub>📊 <b><a href=\"" + live_url + "\">Open the interactive "
                        "Visual Memory Recap</a></b> — the diff annotated against memory, "
                        "the belief card, and the evidence graph Sentinel traversed"
                        + (f" (<a href=\"{run_url}\">run artifact</a>)" if run_url else "")
                        + ".</sub>"
                    )
                elif run_url:
                    recap_note = (
                        "\n\n<sub>📊 <b>Visual Memory Recap</b> — an interactive, annotated "
                        f"walkthrough of this memory conflict is attached as an artifact on "
                        f"<a href=\"{run_url}\">this workflow run</a>.</sub>"
                    )
        except Exception as exc:  # noqa: BLE001 — advisory: the recap is a bonus, not required
            print(f"visual recap skipped: {exc}")

    comment = render_comment(verdict, graph_section) + recap_note

    print("\n" + comment + "\n")
    _write_summary(comment)

    if verdict.should_flag:
        # GitHub Actions annotation — surfaces in the PR checks UI.
        print(f"::warning title=Sentinel::This PR reverses {verdict.decision_reference}")
        if mode == "post":
            post_comment(comment)
            print("-> posted comment to PR")
    elif verdict.suppressed_by_feedback:
        print(f"-> reversal of {verdict.decision_reference} muted by prior '/sentinel noise' feedback")

    return 0  # advisory: never fail the build


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
