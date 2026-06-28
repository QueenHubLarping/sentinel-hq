"""
Reversal detection — the core Sentinel loop.

Given an incoming PR, we:
  1. recall  — pull the relevant past decisions + their reasoning from the Cognee
     graph (multi-hop context; this is the memory the LLM is NOT allowed to invent).
  2. judge   — ask the LLM, grounded ONLY in that retrieved context, whether the PR
     reverses a past decision, and to cite the decision + its original "why".

Cognee = memory (recall). The LLM = reasoning over retrieved facts. The LLM never
decides from its own knowledge — if the contradicted decision isn't in the graph
context, the verdict is "no reversal".
"""

from pydantic import BaseModel, Field

import cognee

GC = cognee.SearchType.GRAPH_COMPLETION


class Verdict(BaseModel):
    """Structured judgment about whether a PR reverses a past decision."""

    reverses_decision: bool = Field(
        description="True only if the PR contradicts/undoes a decision present in the MEMORY CONTEXT."
    )
    decision_reference: str = Field(
        default="",
        description="The reversed decision, e.g. 'ADR-001 (async email)'. Empty if none.",
    )
    original_reasoning: str = Field(
        default="",
        description="WHY the original decision was made, quoted from the memory context.",
    )
    impact_if_merged: str = Field(
        default="",
        description="What regresses if this PR merges (e.g. reintroduced latency).",
    )
    confidence: float = Field(
        default=0.0, description="Confidence 0.0-1.0 that this is a genuine reversal."
    )


_SYSTEM_PROMPT = """You are Sentinel, an institutional-memory guardian for a codebase.
You are given an incoming pull request and MEMORY CONTEXT containing the team's past
engineering decisions and the reasoning behind them. Decide whether the PR REVERSES or
CONTRADICTS a past decision found in the MEMORY CONTEXT.

You MUST fill EVERY field, taking content only from the MEMORY CONTEXT (never invent):
- reverses_decision: true if the PR undoes/contradicts a decision in the context; else false.
- decision_reference: the decision's identifier from the context (e.g. "ADR-001 (async
  email)"). If reverses_decision is true this MUST be non-empty and copied from the context.
- original_reasoning: the WHY, quoted from the context.
- impact_if_merged: concretely what regresses if merged (e.g. "reintroduces the 800ms
  blocking SMTP call in checkout, raising p95 latency"). Non-empty if reverses_decision is true.
- confidence: a number 0.0-1.0. If reverses_decision is true, use 0.7-0.95.

A PR that re-introduces something a past decision deliberately removed IS a reversal.
If the contradicted decision is not in the MEMORY CONTEXT, set reverses_decision=false.

Example — PR makes a queued operation synchronous; context has "ADR-007: use async X to
cut latency". Correct output: reverses_decision=true, decision_reference="ADR-007 (async X)",
original_reasoning="async X was adopted to remove latency from the critical path",
impact_if_merged="reintroduces the latency ADR-007 removed", confidence=0.9.
"""


async def _recall_context(query: str) -> str:
    """Pull the relevant decision context from the graph (no LLM answer, just evidence)."""
    res = await cognee.search(query, query_type=GC, only_context=True)
    return str(res)


async def detect_reversal(pr_text: str, retrieval_query: str | None = None) -> Verdict:
    """Run the recall→judge loop on an incoming PR and return a structured Verdict."""
    from cognee.infrastructure.llm.LLMGateway import LLMGateway

    # 1. recall — what past decisions does this change touch?
    query = retrieval_query or pr_text[:500]
    context = await _recall_context(query)

    # 2. judge — grounded strictly in the retrieved context
    judge_input = (
        f"=== INCOMING PULL REQUEST ===\n{pr_text}\n\n"
        f"=== MEMORY CONTEXT (past decisions + reasoning) ===\n{context}\n"
    )
    verdict = await LLMGateway.acreate_structured_output(
        text_input=judge_input,
        system_prompt=_SYSTEM_PROMPT,
        response_model=Verdict,
    )

    # Small local models don't emit a calibrated confidence float (they leave it 0.0).
    # When that happens, derive a transparent confidence from how completely the
    # grounded fields were filled — a consistency signal, not a model probability.
    if verdict.reverses_decision and verdict.confidence == 0.0:
        filled = sum(
            bool(x) for x in (verdict.decision_reference, verdict.original_reasoning, verdict.impact_if_merged)
        )
        verdict.confidence = round(0.5 + 0.15 * filled, 2)  # 0.65–0.95

    return verdict
