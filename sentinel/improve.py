"""
improve — the team's 👎 becomes durable graph memory that suppresses a drift.

Sentinel is a detective, not a judge. When it raises a reversal flag the team
considers NOISE (an unhelpful false-positive pattern — *not* an intentional override
of the decision), a maintainer replies ``/sentinel noise``. That feedback is written
back into the SAME Cognee graph as a feedback record (``cognee.add`` + ``cognee.cognify``,
tagged ``node_set="sentinel_feedback"``), so the next recall carries it and Sentinel
stops raising that drift. This is the ``improve`` verb.

Honest-minimal (REQUIREMENTS §5): a feedback label keyed on the *drift signature*
(the contradicted decision, e.g. ``ADR-001``). No model, no training — memory the
team writes, that demonstrably changes the next run's behaviour.

Two different human actions → two different memory mutations (don't conflate them):
  ``/sentinel intentional`` → forget  : the decision was deliberately overridden; RETIRE it.
  ``/sentinel noise``       → improve : this FLAG is unhelpful; SUPPRESS this drift type.

The suppression check (``is_dismissed``) is deterministic: it scans the graph for a
machine-parseable marker, so behaviour-change does not hinge on the LLM happening to
recall the feedback node — which is what makes the before/after demo reliable.
"""

import os
import re
from pathlib import Path
from uuid import uuid5

import cognee
from cognee.tasks.ingestion.data_item import DataItem

from sentinel.ingest import DATASET_NAME, _SENTINEL_NS, adr_dir
from sentinel.resolve import _adr_number

FEEDBACK_NODE_SET = "sentinel_feedback"

# Distinctive, machine-parseable marker so dismissals can be found deterministically
# in the graph (a substring scan over node data), independent of LLM recall.
_MARKER = "SENTINEL-DISMISSED-DRIFT"
_MARKER_RE = re.compile(rf"{_MARKER}:\s*([A-Za-z0-9\-]+)")


def feedback_signature(decision_reference: str) -> str:
    """Normalize a decision reference into a stable drift signature (the feedback key).

    ADR references collapse to their canonical id ('ADR-001 (async email)' -> 'ADR-001');
    anything else is slugified so it is still a stable, comparable key.
    """
    adr = _adr_number(decision_reference)
    if adr:
        return adr
    slug = re.sub(r"[^a-z0-9]+", "-", (decision_reference or "").lower()).strip("-")
    return slug or "unknown"


def _feedback_doc(signature: str, decision_reference: str, pr_number: int | None, note: str) -> str:
    where = f" on PR #{pr_number}" if pr_number else ""
    body = (
        f"[source_type: SentinelFeedback] [{_MARKER}: {signature}]\n\n"
        f"# Team feedback: the '{signature}' reversal flag was dismissed as noise\n\n"
        f"A maintainer reviewed Sentinel's flag that a change reverses **{decision_reference}**"
        f"{where} and marked it as NOISE — an unhelpful false-positive drift pattern, not an "
        f"intentional override of the decision. Per this team feedback, Sentinel should NOT "
        f"raise the '{signature}' reversal again.\n"
    )
    if note:
        body += f"\nMaintainer note: {note}\n"
    return body


async def record_noise(decision_reference: str, pr_number: int | None = None, note: str = "") -> dict:
    """Write a 👎 into the graph: dismiss the *decision_reference* drift as noise (improve).

    Idempotent — repeated dismissals of the same drift reuse a stable data_id, so a
    second ``/sentinel noise`` just refreshes the existing feedback record.
    """
    signature = feedback_signature(decision_reference)
    doc = _feedback_doc(signature, decision_reference, pr_number, note)
    data_id = uuid5(_SENTINEL_NS, f"feedback::{signature}")

    item = DataItem(data=doc, label=f"feedback-{signature}.md", data_id=data_id)
    await cognee.add(item, dataset_name=DATASET_NAME, node_set=[FEEDBACK_NODE_SET])
    await cognee.cognify(datasets=[DATASET_NAME])

    # Also invoke the native verb where supported — it weights feedback into recall.
    # Non-fatal: the deterministic marker scan is what guarantees the suppression.
    try:
        await cognee.improve(DATASET_NAME)
    except Exception:
        pass

    return {"status": "recorded", "signature": signature, "decision": decision_reference}


async def graph_dismissed_signatures() -> set[str]:
    """Drift signatures dismissed *in the graph* — a deterministic marker scan.

    This is what powers the local before/after proof (the graph persists between runs
    on a dev box), and does not depend on the LLM surfacing the feedback node.
    """
    from cognee.infrastructure.databases.graph import get_graph_engine

    nodes, _ = await (await get_graph_engine()).get_graph_data()
    found: set[str] = set()
    for node in nodes:
        for m in _MARKER_RE.finditer(str(node)):
            found.add(m.group(1))
    return found


# --- Durable dismissal store (the CI-safe half of improve) ------------------
# A self-hosted runner reinstalls the action each run, so the Cognee graph does not
# survive between a '/sentinel noise' run and the next detection — exactly the same
# constraint forget handles by committing ADR status to the repo. So the 👎 is also
# recorded as a one-line-per-signature file committed to the consuming repo, which the
# next detection reads. (Local dev has no GITHUB_WORKSPACE and relies on the graph.)

def dismissed_file() -> Path:
    """Path to the durable dismissal store, next to the ADRs Sentinel reads."""
    return adr_dir() / ".sentinel-dismissed"


def file_dismissed_signatures() -> set[str]:
    """Drift signatures dismissed in the committed file (empty if the file is absent)."""
    path = dismissed_file()
    if not path.exists():
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


def record_noise_file(decision_reference: str) -> Path:
    """Append this drift's signature to the durable dismissal file (idempotent)."""
    signature = feedback_signature(decision_reference)
    path = dismissed_file()
    existing = file_dismissed_signatures()
    if signature not in existing:
        path.parent.mkdir(parents=True, exist_ok=True)
        header = "" if path.exists() else "# Drift signatures the team dismissed via '/sentinel noise'.\n"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"{header}{signature}\n")
    return path


async def dismissed_signatures() -> set[str]:
    """All dismissed drift signatures: the durable file (CI) ∪ the graph (local)."""
    return file_dismissed_signatures() | await graph_dismissed_signatures()


async def is_dismissed(decision_reference: str) -> bool:
    """True if the team has marked this decision's drift as noise (👎)."""
    return feedback_signature(decision_reference) in await dismissed_signatures()
