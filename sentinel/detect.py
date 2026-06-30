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

# Caps on the judge prompt — keep it small so CPU inference stays fast (prompt
# processing dominates latency on a self-hosted runner without a GPU).
_PR_CHAR_CAP = 2500
_CONTEXT_CHAR_CAP = 3500


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
        description="The reversed decision, PR-keyed, e.g. 'PR #42 (async email)'. Copy the "
        "establishing PR number from the MEMORY CONTEXT (look for [pr_number: NN] or 'PR #NN'). "
        "Empty if none.",
    )
    original_reasoning: str = Field(
        default="",
        description="WHY the original decision was made, quoted from the memory context "
        "(the rationale lives in the linked incident ISSUE, not the PR diff).",
    )
    impact_if_merged: str = Field(
        default="",
        description="What regresses if this PR merges (e.g. reintroduced latency).",
    )
    assumption: str = Field(
        default="",
        description="The load-bearing ASSUMPTION the original decision rests on, quoted/"
        "paraphrased from the context (e.g. 'synchronous email adds ~600ms, exceeding the "
        "checkout latency budget'). Empty if the context states no assumption — never invent one.",
    )
    affected_capability: str = Field(
        default="",
        description="The cross-cutting capability this touches, ONE or two words "
        "(e.g. 'Messaging', 'Payments', 'Rate Limiting'). Empty if unclear.",
    )
    evidence_chain: str = Field(
        default="",
        description="The reconstruction path through the graph, e.g. "
        "'PR #42 (made it async) -> Issue #91 (the latency incident)'. Use the PR/issue "
        "identifiers present in the context. Empty if not derivable.",
    )
    confidence: float = Field(
        default=0.0, description="Confidence 0.0-1.0 that this is a genuine reversal."
    )
    suppressed_by_feedback: bool = Field(
        default=False,
        description="(system-managed — always leave false) set by Sentinel when the team "
        "previously dismissed this drift via '/sentinel noise'.",
    )
    provenance_tier: str = Field(
        default="inferred",
        description="(system-managed — always leave as the default) the trust tier of the "
        "contradicted memory; Sentinel sets 'approved' or 'inferred' after the verdict.",
    )

    @property
    def should_flag(self) -> bool:
        """Whether Sentinel actually surfaces this: a reversal the team hasn't muted."""
        return self.reverses_decision and not self.suppressed_by_feedback


_SYSTEM_PROMPT = """You are Sentinel, an institutional-memory guardian for a codebase.
You are given an incoming pull request and MEMORY CONTEXT containing the team's past
engineering decisions and the reasoning behind them. Decide whether the PR REVERSES or
CONTRADICTS a past decision found in the MEMORY CONTEXT.

Reading the diff correctly is critical: lines starting with '-' are REMOVED by the PR,
lines starting with '+' are ADDED. The PR's net effect = it deletes the '-' code and
introduces the '+' code. Do not confuse the PR's change with the existing decision.

You MUST fill EVERY field, taking content only from the MEMORY CONTEXT (never invent):
- reverses_decision: true if the PR undoes/contradicts a decision in the context; else false.
- decision_reference: the decision's identifier from the context, PR-keyed (e.g. "PR #42
  (async email)"). Look for [pr_number: NN] or "PR #NN" in the context. If reverses_decision
  is true this MUST be non-empty and copied from the context.
- original_reasoning: the WHY, quoted from the context (it lives in the linked incident ISSUE).
- impact_if_merged: concretely what regresses if merged (e.g. "reintroduces the 800ms
  blocking SMTP call in checkout, raising p95 latency"). Non-empty if reverses_decision is true.
- assumption: the load-bearing assumption the decision rests on, IF the context states one
  (e.g. "the provider call costs ~800ms on the critical path"); else leave empty — never invent.
- affected_capability: one/two words for the capability (e.g. "Messaging"); empty if unclear.
- evidence_chain: the path through the context, e.g. "PR #42 (made it async) -> Issue #91
  (the latency incident)"; use the identifiers present; empty if not derivable.
- confidence: a number 0.0-1.0. If reverses_decision is true, use 0.7-0.95.

A PR that re-introduces something a past decision deliberately removed IS a reversal.
Common reversal patterns to catch:
- the context says a thing was made ASYNC / moved to a QUEUE / made NON-BLOCKING for a
  reason, and the PR makes it SYNCHRONOUS / INLINE / BLOCKING again.
- the context says a library/pattern was REMOVED/REPLACED, and the PR brings it back.
Think step by step: identify the decision in the context, identify what the PR changes,
then check if the PR undoes the decision. If the contradicted decision is not in the
MEMORY CONTEXT, set reverses_decision=false.

Example — PR makes a queued operation synchronous; context has "PR #42 (async X): moved X to
a queue" and "Issue #91: X on the critical path cost ~800ms latency". Correct output:
reverses_decision=true, decision_reference="PR #42 (async X)", original_reasoning="X was moved
off the critical path to remove ~800ms of latency", impact_if_merged="reintroduces the latency
PR #42 removed", assumption="X on the critical path costs ~800ms", evidence_chain="PR #42
(made it async) -> Issue #91 (the latency incident)", affected_capability="Messaging",
confidence=0.9.
"""


def _recall_query(pr_text: str) -> str:
    """The recall question Sentinel asks the graph for an incoming change.

    Factored out so the Improve phase can replay the *identical* query inside a
    session — guaranteeing its 👎 feedback lands on the same graph nodes/edges that
    produced the flag.
    """
    return (
        "What past engineering decision relates to the following change, and what was the "
        f"reasoning behind it? Quote specifics.\n\nChange:\n{pr_text[:800]}"
    )


async def _recall_context(
    pr_text: str,
    *,
    session_id: str | None = None,
    feedback_influence: float | None = None,
    top_k: int | None = None,
) -> str:
    """Pull the relevant decision(s) for this PR as a coherent summary (decision + why).

    A GRAPH_COMPLETION answer is more robust judge input than the raw only_context blob,
    whose shape varies between cognify builds. We also include the raw context as backup.

    Improve-phase knobs (all optional; defaults preserve the original behavior):
      session_id         — record the completion search as a Cognee session Q&A entry, so
                           the Improve phase can attach 👍/👎 feedback to the exact graph
                           elements it used (see sentinel.improve).
      feedback_influence — weight (0..1) the retriever gives to learned feedback when
                           ranking triplets; >0 makes earlier 👎 down-rank that memory.
      top_k              — cap on retrieved triplets (tighter cap = sharper suppression).
    """
    question = _recall_query(pr_text)

    # Build kwargs lazily so an unconfigured call hits cognee.search with its own
    # defaults — keeping day2/day3 detection byte-for-byte unchanged.
    tuning: dict = {}
    if feedback_influence is not None:
        tuning["feedback_influence"] = feedback_influence
    if top_k is not None:
        tuning["top_k"] = top_k

    # Only the completion search runs inside the session: it is the one that records
    # used_graph_element_ids. The only_context probe stays session-less so it never adds
    # a second, answer-less Q&A entry that would muddy which recall the feedback targets.
    answer = await cognee.search(
        question,
        query_type=GC,
        **({"session_id": session_id} if session_id else {}),
        **tuning,
    )
    raw = await cognee.search(question, query_type=GC, only_context=True, **tuning)
    return (" ".join(str(r) for r in answer) if answer else "") + "\n\n" + str(raw)


def _normalize_confidence(c: float) -> float:
    """Normalize an LLM-emitted confidence value to [0.0, 1.0].

    Some models emit 85 instead of 0.85; divide by 100 when the value exceeds 1.
    """
    return max(0.0, min(1.0, c / 100.0 if c > 1.0 else c))


async def detect_reversal(
    pr_text: str,
    retrieval_query: str | None = None,
    *,
    session_id: str | None = None,
    feedback_influence: float | None = None,
    top_k: int | None = None,
) -> Verdict:
    """Run the recall→judge loop on an incoming PR and return a structured Verdict.

    The optional session_id / feedback_influence / top_k flow straight through to recall
    (see _recall_context). With them, detection becomes the front half of the Improve
    loop: pass a session_id so the flag's recall is recorded, and feedback_influence>0 so a
    later 👎 (via sentinel.improve) actually suppresses the next detection. Omit them and
    detection behaves exactly as in Day 2/3.
    """
    from cognee.infrastructure.llm.LLMGateway import LLMGateway

    # 1. recall — what past decisions does this change touch?
    context = await _recall_context(
        retrieval_query or pr_text,
        session_id=session_id,
        feedback_influence=feedback_influence,
        top_k=top_k,
    )

    # 2. judge — grounded strictly in the retrieved context.
    # Cap both inputs: CPU prompt-processing is the dominant cost on a self-hosted
    # runner (~10 tok/s for a 7B), so a 4k-token prompt is minutes of latency before
    # generation even starts. The GRAPH_COMPLETION answer (which leads `context`) holds
    # the decision+why; trimming the raw blob tail keeps the signal and slashes latency.
    judge_input = (
        f"=== INCOMING PULL REQUEST ===\n{pr_text[:_PR_CHAR_CAP]}\n\n"
        f"=== MEMORY CONTEXT (past decisions + reasoning) ===\n{context[:_CONTEXT_CHAR_CAP]}\n"
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

    # improve: if the team previously dismissed this drift as noise ('/sentinel noise'),
    # the flag is muted. The judgment stays honest (reverses_decision is unchanged); we
    # only suppress surfacing it. Read live from the graph, so it changes the next run.
    verdict.suppressed_by_feedback = False
    if verdict.reverses_decision and verdict.decision_reference:
        from sentinel.improve import is_dismissed

        verdict.suppressed_by_feedback = await is_dismissed(verdict.decision_reference)

    # Trust tier (minimal M9 / §8.1): only HUMAN-APPROVED memory drives a confident flag;
    # machine-INFERRED memory surfaces as a soft "possible" proposal. The tier is set here,
    # never by the LLM, from the human-approval ledger (sentinel.trust). The comment card
    # renders confident vs. soft off this — the asymmetry rule made visible.
    if verdict.reverses_decision and verdict.decision_reference:
        from sentinel.trust import provenance_tier

        verdict.provenance_tier = provenance_tier(verdict.decision_reference)

    return verdict
