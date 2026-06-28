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
    """Structured judgment about whether a PR reverses a past decision.

    Field order matters: `analysis` comes first so the model reasons (chain-of-thought)
    BEFORE committing to the boolean — this markedly improves small-model accuracy.
    """

    analysis: str = Field(
        description="Reason here FIRST, in this exact order: "
        "(1) PR EFFECT — in the diff, '-' lines are REMOVED and '+' lines are ADDED; state "
        "plainly what the PR removes and what it adds (e.g. 'removes async Celery dispatch, "
        "adds synchronous SMTP call'). "
        "(2) DECISION — what the MEMORY CONTEXT decided and why. "
        "(3) CONFLICT — does the PR's effect undo the decision?"
    )
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

Reading the diff correctly is critical: lines starting with '-' are REMOVED by the PR,
lines starting with '+' are ADDED. The PR's net effect = it deletes the '-' code and
introduces the '+' code. Do not confuse the PR's change with the existing decision.

You MUST fill EVERY field, taking content only from the MEMORY CONTEXT (never invent):
- reverses_decision: true if the PR undoes/contradicts a decision in the context; else false.
- decision_reference: the decision's identifier from the context (e.g. "ADR-001 (async
  email)"). If reverses_decision is true this MUST be non-empty and copied from the context.
- original_reasoning: the WHY, quoted from the context.
- impact_if_merged: concretely what regresses if merged (e.g. "reintroduces the 800ms
  blocking SMTP call in checkout, raising p95 latency"). Non-empty if reverses_decision is true.
- confidence: a number 0.0-1.0. If reverses_decision is true, use 0.7-0.95.

A PR that re-introduces something a past decision deliberately removed IS a reversal.
Common reversal patterns to catch:
- the context says a thing was made ASYNC / moved to a QUEUE / made NON-BLOCKING for a
  reason, and the PR makes it SYNCHRONOUS / INLINE / BLOCKING again.
- the context says a library/pattern was REMOVED/REPLACED, and the PR brings it back.
Think step by step: identify the decision in the context, identify what the PR changes,
then check if the PR undoes the decision. If the contradicted decision is not in the
MEMORY CONTEXT, set reverses_decision=false.

Example — PR makes a queued operation synchronous; context has "ADR-007: use async X to
cut latency". Correct output: reverses_decision=true, decision_reference="ADR-007 (async X)",
original_reasoning="async X was adopted to remove latency from the critical path",
impact_if_merged="reintroduces the latency ADR-007 removed", confidence=0.9.
"""


async def _recall_context(pr_text: str) -> str:
    """Pull the relevant decision(s) for this PR as a coherent summary (decision + why).

    A GRAPH_COMPLETION answer is more robust judge input than the raw only_context blob,
    whose shape varies between cognify builds. We also include the raw context as backup.
    """
    question = (
        "What past engineering decision relates to the following change, and what was the "
        f"reasoning behind it? Quote specifics.\n\nChange:\n{pr_text[:800]}"
    )
    answer = await cognee.search(question, query_type=GC)
    raw = await cognee.search(question, query_type=GC, only_context=True)
    return (" ".join(str(r) for r in answer) if answer else "") + "\n\n" + str(raw)


def _normalize_confidence(c: float) -> float:
    """Normalize an LLM-emitted confidence value to [0.0, 1.0].

    Some models emit 85 instead of 0.85; divide by 100 when the value exceeds 1.
    """
    return max(0.0, min(1.0, c / 100.0 if c > 1.0 else c))


async def detect_reversal(pr_text: str, retrieval_query: str | None = None) -> Verdict:
    """Run the recall→judge loop on an incoming PR and return a structured Verdict."""
    from cognee.infrastructure.llm.LLMGateway import LLMGateway

    # 1. recall — what past decisions does this change touch?
    context = await _recall_context(retrieval_query or pr_text)

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

    verdict.confidence = _normalize_confidence(verdict.confidence)

    # Small local models sometimes leave confidence at 0.0. When that happens,
    # derive a transparent proxy from how fully the grounded fields were filled —
    # a consistency signal, not a model probability.
    if verdict.reverses_decision and verdict.confidence == 0.0:
        filled = sum(
            bool(x) for x in (verdict.decision_reference, verdict.original_reasoning, verdict.impact_if_merged)
        )
        verdict.confidence = round(0.5 + 0.15 * filled, 2)  # 0.65–0.95

    return verdict
