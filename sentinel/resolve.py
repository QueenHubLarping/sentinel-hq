"""
Handle the human-in-the-loop decision: '/sentinel intentional'.

Sentinel is a detective, not a judge — it flags and asks; the team decides. When a
maintainer confirms an override is intentional, the contradicted decision is RETIRED
from memory (forget). After that, re-detecting the same PR yields no reversal — the
decision it was protecting no longer exists. This is the forget -> behavior-change loop.

NOTE: this retires at dataset granularity, which fits the single-decision demo corpus.
The Day-4 refinement is node-level retire (mark the one decision active->retired) so
unrelated decisions in a larger graph survive.
"""

import cognee

from sentinel.ingest import DATASET_NAME


async def mark_intentional(decision_reference: str = "") -> dict:
    """Retire the superseded decision so Sentinel stops flagging PRs that follow it."""
    return await cognee.forget(dataset=DATASET_NAME)
