"""
Handle the human-in-the-loop decision: '/sentinel intentional'.

Sentinel is a detective, not a judge — it flags and asks; the team decides. When a
maintainer confirms an override is intentional, the contradicted decision is RETIRED
from memory (forget). After that, re-detecting the same PR yields no reversal — the
decision it was protecting no longer exists. This is the forget -> behavior-change loop.

Selective forget: only the specific corpus document whose label matches the contradicted
decision (e.g. "ADR-001-async-email.md") is removed via cognee.forget(data_id=...).
Graph nodes and vector embeddings for that document are deleted; every other decision in
the dataset stays intact.
"""

import cognee

from sentinel.ingest import DATASET_NAME


async def mark_intentional(decision_reference: str = "") -> dict:
    """Retire the superseded decision using cognee.forget, scoped to that one file.

    Finds the corpus data item whose label contains the decision key (e.g. 'ADR-001'),
    then calls cognee.forget(data_id=item.id, dataset=DATASET_NAME) which surgically
    removes only that document's graph nodes and vector entries.
    """
    from cognee.low_level import setup
    from cognee.modules.users.methods import get_default_user
    from cognee.api.v1.datasets.datasets import datasets

    await setup()
    user = await get_default_user()

    # Locate the sentinel_decisions dataset.
    user_datasets = await datasets.list_datasets(user=user)
    dataset = next((d for d in user_datasets if d.name == DATASET_NAME), None)
    if dataset is None:
        return {"status": "error", "note": f"Dataset '{DATASET_NAME}' not found."}

    # Find corpus data items whose label (filename) contains the decision key.
    data_items = await datasets.list_data(dataset.id, user=user)
    key = decision_reference.split("(")[0].strip().lower()  # e.g. "adr-001"

    matching = [
        item for item in data_items
        if key in str(getattr(item, "label", "") or "").lower()
        or key in str(item.name or "").lower()
    ]

    if not matching:
        return {
            "status": "not_found",
            "decision": decision_reference,
            "searched_key": key,
            "note": (
                "No corpus data item matched. The graph was likely built before "
                "DataItem labels were introduced — re-run ingest to rebuild."
            ),
        }

    # cognee.forget(data_id=..., dataset=...) calls delete_data_nodes_and_edges
    # for the specific item, leaving all other decisions untouched.
    retired = []
    for item in matching:
        result = await cognee.forget(data_id=item.id, dataset=DATASET_NAME)
        retired.append({
            "data_id": str(item.id),
            "label": str(getattr(item, "label", None) or item.name),
            "result": result,
        })

    return {
        "status": "retired",
        "decision": decision_reference,
        "retired_items": len(retired),
        "items": retired,
    }
