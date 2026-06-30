"""Memory trust tiers — `inferred` vs. `human-approved` (the minimal M9 gating).

Two orthogonal axes (PRODUCT_SPEC §8.1): **confidence** (how well-evidenced) is distinct
from **provenance tier** (who stands behind it). This module owns the second axis.

- **inferred** — extracted by `cognify` from PR/issue text; nobody confirmed it. The
  *fluid* tier: it may only *propose* ("possible — confirm?"), never drive a confident flag.
  Everything bootstrapped is born `inferred` (history is not human ratification).
- **approved** — a person stood behind it (`/sentinel intentional`, a 👍, or answering
  Sentinel's one-line question). The *sticky* tier and the only one allowed to drive a
  confident reversal flag.

A decision becomes `approved` when its PR number is in the approved-list — the union of:
  - `$SENTINEL_APPROVED_PRS`            (comma-separated PR numbers; demo/CI convenience), and
  - `.sentinel/approved.json`           (a JSON list of PR numbers; the durable record).

The demo pre-seeds the established decisions as approved *history* — allowed under the
honesty rule (PRODUCT_SPEC §11): it is a pre-seeded *input*, not a claimed-live output.
"""

import json
import os

from sentinel.resolve import _pr_number
from sentinel.retired import sentinel_dir

INFERRED = "inferred"
APPROVED = "approved"


def _approved_file_path():
    return sentinel_dir() / "approved.json"


def approved_pr_numbers() -> set[int]:
    """PR numbers whose decision a human has approved (env ∪ `.sentinel/approved.json`)."""
    out: set[int] = set()

    raw = os.environ.get("SENTINEL_APPROVED_PRS", "")
    for tok in raw.replace(",", " ").split():
        try:
            out.add(int(tok))
        except ValueError:
            pass

    path = _approved_file_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for n in data if isinstance(data, list) else []:
                try:
                    out.add(int(n))
                except (TypeError, ValueError):
                    pass
        except Exception:  # noqa: BLE001 — a bad file must not break detection
            pass
    return out


def provenance_tier(decision_reference: str) -> str:
    """`approved` if the referenced decision's PR is human-approved, else `inferred`.

    Conservative by design: an unknown/unparseable reference is `inferred`, so Sentinel
    never drives a *confident* flag off memory nobody has ratified (the asymmetry rule).
    """
    pr = _pr_number(decision_reference)
    if pr is not None and pr in approved_pr_numbers():
        return APPROVED
    return INFERRED
