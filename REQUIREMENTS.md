# Sentinel — Requirements & Goals

> Decision-reversal guardian for code review, built on Cognee.
> Hackathon: Cognee "Hangover Part AI" (Jun 29 – Jul 5, 2026). Track: **Best Use of Open Source** (self-host).
> Team: Chayan, Rudradeep, Abhijit.

Synthesized from a 4-way adversarial design debate (Ambition vs Pragmatist vs Judge/Red-team vs Demo). Where they conflicted, the resolution is recorded inline.

---

## 1. North-star goal
A judge watches **Cognee's own repo** get a PR that silently reverses a past engineering decision. Sentinel auto-comments with the *original reasoning trail* (pulled by multi-hop graph traversal). The maintainer marks it "intentional" → the graph **forgets** the old decision live → the **same PR is no longer flagged.** The judge walks away thinking: *"that's the only team that used memory as a living system — not a vector search with extra steps."*

We are not building a linter. We are building **institutional memory that reasons, learns, and forgets — visibly.**

## 2. The non-negotiable spine (build FIRST — this is where the hackathon is won)
The "Best Use of Cognee" criterion exists to filter out exactly our competitors. We win it by proving two things *on screen*, and we build them before anything else:

- **SPINE-1 — Real multi-hop recall the graph alone enables.** At least one flag where the reversed decision connects to its rationale through **≥2 typed-edge hops across ≥2 source types** (ADR ↔ PR ↔ "Slack"/commit), with **no lexical overlap**, so pure vector search demonstrably misses it. We must be able to say: *"vector-only returns nothing here; the `supersedes`/`justified_by` edges are what make recall correct."*
- **SPINE-2 — `forget` and `improve` as visible graph mutations.** Show the graph state via query/viz **before** and **after** a supersession (node retired/edge re-pointed) and after a 👎 (a drift-type drops below threshold and stops surfacing). Behavior change must be **inspectable as a before/after diff, not narrated.**

If we cannot demo SPINE-1 and SPINE-2, we lose the differentiator regardless of polish. Everything else serves these.

## 3. Target user & problem
- **User:** a developer/maintainer reviewing a PR, especially in a fast-moving team with no one to give full historical context.
- **Problem:** codebases remember *what* changed, never *why*. Months later a "simplify" PR silently undoes a deliberate decision nobody remembers the reason for → avoidable regressions.
- **Wedge vs CodeRabbit/Gemini:** they review a diff against the internet's conventions, in isolation, every time. Sentinel remembers *why this codebase is the way it is*, across PRs and sources, and learns the team's **non-standard, intentional conventions.** One line: *"They review against the internet's conventions. We review against yours."*

## 4. Functional requirements (MoSCoW)

### MUST (the MVP — the thing that wins)
- **M1.** Self-hosted Cognee ingesting a **real curated decision corpus** from one repo (Cognee's own): ADRs + linked PRs/commits + 2–3 static "Slack" markdown docs. (`remember`)
- **M2.** On a PR, **multi-hop recall** retrieves the contradicted decision **and its WHY** (reasoning + author + date + source links). Real traversal, not string match. (`recall`)
- **M3.** A **GitHub Action** that triggers on PR open, runs end-to-end in <30s, and posts a **natively-styled** comment citing the graph-sourced evidence chain. No citation → no comment.
- **M4.** Human-in-the-loop control ("Intentional / Supersede" label or bot-reply parse) that triggers a **real `forget`** (retire old decision node, latest-wins). (`forget`)
- **M5.** Re-running detection after a forget returns a **different result** (the flag disappears) — detection reads live graph state, never a cached verdict.
- **M6.** 👍/👎 feedback **stored and queryable**, and a 👎 **demonstrably suppresses** a similar future flag. (`improve`)
- **M7.** **Curated graph visualization** (6–8 relevant nodes, before/after states) — for the demo and as Best-Use-of-Cognee evidence.
- **M8.** ONE contradiction type, done flawlessly (recommended: an architecture/config choice reversed, e.g. "async email chosen to cut 800ms latency" → PR makes it sync again).

### SHOULD (if core is solid by Day 4)
- **S1.** Confidence threshold + "noise budget" — only surface flags above confidence; visible precision number on a real PR set ("N PRs, M flags, K confirmed").
- **S2.** Auto-drafted superseding ADR when a maintainer confirms "intentional."
- **S3.** Incremental ingestion (only new PRs per Action run).

### WON'T (this hackathon — explicit cuts)
- **W1.** Live Slack API ingestion → use static markdown instead. (Keeps cross-source multi-hop, drops auth/scraping risk.)
- **W2.** MCP "ask-the-graph" second face → **stretch only**, one person, **Day-4 kill switch**; otherwise a "future work" slide.
- **W3.** Multiple contradiction types, multi-repo, generality → slide bullets, not demo code.
- **W4.** Any ML training for `improve` → feedback-weighted lookup only (see §5).
- **W5.** Dependence on a live webhook round-trip during the demo (see §7).

## 5. The 4 verbs — cheapest *honest* version of each
The word "honest": judges will sniff a fake. Real but minimal.
- **remember** — Real. Ingest the curated corpus (decisions + reasoning + relationships). Do not shrink; this is the scoring surface.
- **recall** — Real. Genuine multi-hop traversal (PR change → component → governing decision → reasoning/author/date). The money shot. Never fake.
- **forget** — A `supersedes` edge + active/retired flag, latest-wins. On "intentional," write a new decision node and retire the old (kept for history, excluded from active recall). No GC/tombstone infra. Honest because retirement genuinely changes future behavior.
- **improve** — 👍/👎 → a weight/label store keyed on drift-type or file path. 👎 marks a drift pattern as noise; recall down-ranks/suppresses it next time. No model. Honest because feedback genuinely alters the next run. Frame the ranking model as "future work."

## 6. Success criteria (measurable — from the judge red-team)
Top-tier if we can check 5+; **losing #3 and #4 means losing Best Use of Cognee, full stop:**
1. Real-repo catch: ≥1 genuine reversal flagged on a repo we did NOT author, with correct citations.
2. Multi-hop proof: ≥1 catch needing ≥2 typed hops across ≥2 source types where vector-only is shown to miss it.
3. `forget` proven on screen: before/after graph query; same PR no longer flagged after.
4. `improve` proven on screen: a dismissed drift type stops surfacing after feedback.
5. A stated precision ratio on real PRs (even small N).
6. A one-sentence "what breaks if you remove Cognee" everyone on the team can say identically.
7. One-screenshot test: the PR comment alone communicates the value.
8. Reproducibility: the demo re-runs live, not just from a recording.

## 7. Demo requirements (5 min) & honesty rule
- **Beats:** Hook (the wound) → REMEMBER (graph exists) → RECALL (the catch, land it slow, 3s silence) → IMPROVE (detective not judge, 30s, compressible) → **FORGET = THE WOW** (mark intentional → graph mutates live → identical PR now silent) → Close (the positioning line).
- **The single WOW:** *same PR, opposite behavior, because memory was forgotten.* Protect REMEMBER→RECALL→FORGET; `improve` is the cut-for-time beat. Rehearse to 4:30.
- **Honesty rule (live vs seeded):** pre-seed *inputs and history* (ingestion, corpus, prior 👍/👎). **Never** pre-seed *the outputs you claim the AI produced live* — the recall comment, the forget mutation, and the behavior flip must be generated live. Volunteer this distinction to judges; it builds trust.

## 8. Disqualifier / hygiene checklist
- [ ] **Disclose all AI tools used** (incl. Claude Code) in the submission — rules require it.
- [ ] Cognee **self-hosted**, repo **public**, runs **from a clean clone** with one-command setup + README.
- [ ] Permissive **LICENSE** file present (Open Source track).
- [ ] Secrets (GitHub token, LLM keys) via Action secrets — **never committed**.
- [ ] Cognee is on the **live demo path** (a judge grepping for Cognee calls finds them — not stubbed).
- [ ] No dependency on a competitor's platform (it's our own Action).
- [ ] Synthetic/consented data only for any "Slack" content.
- [ ] All submission artifacts (demo video, repo, writeup) within the window.

## 9. Top risks → de-risk
- Cognee unfamiliarity eats days → **Day-1 spike, nothing else.**
- Live demo flakiness → pre-staged PR + on-demand re-run + **recorded honest backup**; never depend on network on stage.
- LLM nondeterminism on the climax comment → pinned model, low temp, tight prompt over retrieved subgraph, known-good fallback.
- Forget doesn't flip behavior → detection must read live graph; second PR a near-clone; rehearse the flip to 100%.
- False positives → one curated type on a controlled corpus + "detective not judge" framing + a control set of PRs it stays silent on.
- Integration hell late → end-to-end skeleton wired by Day 3; **feature freeze after Day 4.**

## 10. Six-day plan (Jun 29 – Jul 5)
- **Day 1 — Cognee spike + corpus.** Self-host running; curate corpus; `remember` working; pick the one contradiction type. **Gate: data in the graph + delete/forget visibly removes a node from recall.**
- **Day 2 — Recall.** Real multi-hop query returns the right decision + WHY (hand-fed PR diff). **Gate: SPINE-1 demonstrable.**
- **Day 3 — End-to-end skeleton.** Action triggers on PR → recall → LLM → posted comment (ugly OK). **Gate: a real PR produces a real comment.**
- **Day 4 — Forget + Improve.** Maintainer reply → supersede/retire (forget) + 👎-weight (improve), so the *next* recall changes. **Gate: SPINE-2 demonstrable. FEATURE FREEZE.**
- **Day 5 — Harden + de-risk demo.** Polish the comment (the climax artifact); pre-stage repo + PR; record backup; lock prompts/fallbacks; curate the graph viz. **Gate: demo runs clean 3× in a row.**
- **Day 6 — Presentation + buffer.** Deck (graph screenshot, 4-verb story, "what breaks without Cognee" line, competitive wedge, MCP as future work). Rehearse to 4:30. Jul 5 = buffer/submission.

## 11. The one sentence that must be true
*Remove Cognee and the product breaks*, because decision-reversal is a **relationship between two distant, differently-worded nodes** — similarity search can't see relationships; typed graph traversal can. That is the whole reason this project exists.
