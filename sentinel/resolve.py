"""
Handle the human-in-the-loop decision: '/sentinel intentional'.

Sentinel is a detective, not a judge — it flags and asks; the team decides. When a
maintainer confirms an override is intentional, the contradicted decision is RETIRED
from memory (forget). After that, re-detecting the same PR yields no reversal — the
decision it was protecting no longer exists. This is the forget -> behavior-change loop.

Selective forget: only the specific corpus document whose filename matches the contradicted
ADR (e.g. "ADR-001-async-email.md") is removed via cognee.forget(data_id=...).
Graph nodes and vector embeddings for that document are deleted; every other decision
in the dataset stays intact.

The data_id used for forget is the same stable UUID that ingest.py assigned at add()
time — derived deterministically from the filename via corpus_file_data_id(). This
avoids going through internal Cognee dataset-listing APIs, which are fragile.
"""

import re

import cognee

from sentinel.ingest import DATASET_NAME, adr_dir, corpus_file_data_id


def _adr_number(decision_reference: str) -> str | None:
    """Extract and normalize an ADR number from a model decision_reference string.

    Handles 'ADR-001 (async email...)', 'ADR-42', 'adr-003 foo', 'ADR 002', etc.
    Returns a zero-padded string like 'ADR-001', or None if no ADR pattern found.
    """
    m = re.search(r"ADR[- ](\d+)", decision_reference, re.IGNORECASE)
    if not m:
        return None
    return f"ADR-{int(m.group(1)):03d}"


async def mark_intentional(decision_reference: str = "") -> dict:
    """Retire the superseded decision using cognee.forget, scoped to that one file.

    Resolves the corpus ADR file from the decision reference (e.g. 'ADR-001'),
    then calls cognee.forget(data_id=..., dataset=DATASET_NAME), which surgically
    removes only that document's graph nodes and vector entries.
    """
    from cognee.low_level import setup

    await setup()

    adr_id = _adr_number(decision_reference)
    if not adr_id:
        return {
            "status": "error",
            "decision": decision_reference,
            "note": (
                f"Could not extract an ADR number from {decision_reference!r}. "
                "Expected a reference containing 'ADR-NNN'."
            ),
        }

    # Locate matching ADR files (e.g. "ADR-001-async-email.md") in the same
    # directory ingest read them from — the consuming repo's docs/adr when running
    # in CI, else the bundled corpus.
    adr_path = adr_dir()
    matches = sorted(adr_path.glob(f"{adr_id}*.md"))
    if not matches:
        return {
            "status": "not_found",
            "decision": decision_reference,
            "adr_id": adr_id,
            "note": (
                f"No ADR file found matching '{adr_id}*.md' in {adr_path}. "
                "Re-run ingest if the ADRs were recently changed."
            ),
        }

    # Retire each matching file using the same stable UUID that ingest.py assigned.
    retired = []
    for path in matches:
        data_id = corpus_file_data_id(path.name)
        result = await cognee.forget(data_id=data_id, dataset=DATASET_NAME)
        retired.append({"data_id": str(data_id), "file": path.name, "result": result})

    return {
        "status": "retired",
        "decision": decision_reference,
        "adr_id": adr_id,
        "retired_items": len(retired),
        "items": retired,
    }
