# Sentinel — Requirements & Goals

> **Sentinel is the Memory OS for software engineering — the Organizational Learning Engine. Every important engineering lesson your team learns becomes impossible to lose.**
> Built on Cognee. Hackathon: Cognee "Hangover Part AI" (Jun 29 – Jul 5, 2026). Track: **Best Use of Open Source** (self-host).
> Team: Chayan, Rudradeep, Abhijit.

This is the requirements/scope doc (MoSCoW, gates, success criteria, risks). The full narrative lives in **`PRODUCT_SPEC.md`** — read it first; this doc operationalizes it. Where the full vision and the 5-day live demo conflict, the resolution is recorded inline.

**Two foundational scope decisions (locked):**
- **No ADRs, no Slack, no separate decision docs as inputs.** Sentinel reconstructs the *why* from **merged PRs, diffs, linked issues, review comments, and human input** — what every repo already has. Decision identity is anchored to the **establishing PR**, not an ADR file. Deployable on any repo with **zero documentation tax**.
- **No `memory/` directory.** Memory lives **in Cognee** (graph + vector), surfaced through the **Memory Review comment** and the **graph visualization**. Durability of a `forget` rests on Cognee's persistent stores + a small non-user-facing `.sentinel/retired.json` skip-list.

---

## 1. Positioning & north-star

**Positioning:** we are not building a better memory system than Cognee — we are building **the best application of Cognee.** Cognee is memory infrastructure; Sentinel is engineering intelligence built on it. *Stripe is to Postgres what Sentinel is to Cognee.*

**North-star demo:** a judge watches Cognee's *own* repo receive a PR that silently reverses a past engineering decision. Sentinel doesn't say "related PRs" — it says **"This PR doesn't just change code; it changes what your organization believes about Messaging,"** and reconstructs the original *lesson* (reasoning + outcome + evidence) by multi-hop traversal across PRs and issues. The maintainer marks it intentional → the graph **forgets** the old learning live → **the same PR is no longer flagged.**

We are not building a linter. We are building **institutional memory that reasons, learns, and forgets — visibly — with no documentation prerequisite.**

---

## 2. The non-negotiable spine (built — protect; one part is being re-anchored)

"Best Use of Cognee" is won by proving two things **on screen**, before any polish:

- **SPINE-1 — Real multi-hop recall only the graph enables.** ≥1 flag where the reversed learning connects to its rationale through a hop recoverable **neither by vector similarity (no shared words) nor by an explicit `#ref` link** — only by graph + semantic reasoning. The discriminating chain: the **incoming PR diff** has no lexical overlap with, and no link to, the **incident issue** holding the rationale; Sentinel connects them through the governing Decision. *(Verify this hop empirically on the new PR/issue corpus — "PR + issue = 2 source types" is trivial; a hop no `#ref` and no shared word can make is the real bar.)*
- **SPINE-2 — `forget` and `improve` as visible graph mutations.** Show graph state (query + viz) **before and after** a supersession (PR-keyed decision node retired / edge re-pointed) and after a 👎 (a drift type drops below threshold and stops surfacing). Behavior change is an **inspectable before/after diff, not narrated.**

Both spines are implemented and proven — but **SPINE-2 is currently proven on ADR-keyed machinery.** The work now: re-anchor to PR/issue and dress the spine in the Memory OS experience **without regressing it.** Capture a known-good baseline run before any change.

> **Sequencing rule (protects the WOW):** build the PR/issue-keyed decision + forget and **re-prove SPINE-2 on it BEFORE deleting the ADR code path.** Never remove working substrate before the replacement is proven, 5 days out.

---

## 3. Target user, problem & personas

- **Problem:** codebases remember *what* changed, never *why*. `git blame` gives an author and a line, never the reasoning, the tradeoff, or the incident that forced the decision. Months later a "simplify" PR silently undoes a deliberate decision nobody remembers → avoidable regressions. **Memory = compression of experience into reusable lessons**; if it can't change future behavior it's an archive, not memory. And teams shouldn't need to have written ADRs to get it.
- **Wedge vs CodeRabbit/Gemini:** they review a diff against the internet's conventions, in isolation, every time. Sentinel remembers *why this codebase is the way it is*. One line: *"They review against the internet's conventions. We review against yours — reconstructed from your own PRs and issues, no docs required."*
- **Personas to optimize for:**
  - **Developer** — never writes docs; occasionally spends 10s confirming "Sentinel understood this."
  - **Reviewer** — never searches Slack/Confluence; the Memory Review answers "why?" before they ask.
  - **New engineer** — opens a file, gets the Engineering Memory (one story) instead of `git blame`. *(Roadmap face.)*
  - **AI agent** (Claude Code / Cursor / Codex) — queries organizational memory instead of re-reading the repo.

---

## 4. The knowledge model (exactly two layers — do not over-normalize)

The graph mirrors **how engineers mentally model the system, not the repo directory tree.**

- **Layer 1 — Capabilities** (navigation entry point): long-lived, cross-cutting, *not* directory-bound — `Messaging`, `Authentication`, `Payments`, `Checkout`. Under them sit **Topics** (`Async Email`, `Retry Policy`).
- **Layer 2 — Knowledge objects** (one shared ontology): `Decision`, `Assumption`, `Experiment`, `Incident`, `Outcome` → compress into a **Learning**. **Decisions are anchored to their establishing PR** (deterministic id from the PR number).
- **Assumptions are first-class — memory is conditional, not absolute.** A decision is `Decision **because** Assumption holds`, so we store the assumption **and the conditions that break it**. An `Assumption` carries: **statement** (the premise, e.g. "sync email adds ~600ms, exceeding checkout's budget"), **invalidation_conditions[]** (thresholded *or* qualitative: "latency drops materially" / "email leaves the critical path" / "budget relaxed"), **status** (`holding | at-risk | invalidated`), and inherits confidence + provenance (§6.1). Edge: `Decision —rests_on→ Assumption —invalid_when→ Condition`. This makes recall *conditional* ("safe **only if** X still holds — is it?"), gives a principled `forget` trigger (a met condition → the decisions on it are supersession candidates), and enables **proactive assumption-drift** (roadmap). **Guardrail:** never fabricate a numeric threshold the history doesn't state — store it qualitatively, mark it inferred (§6).
- **Evidence supports memory, never *is* memory:** `PR` (body + diff), `Issue` (thread + comments), `Review comment`, `Commit`, `Benchmark`. Rationale is mined from issue threads / PR discussion — **never invented from the diff** (§6 guardrail).

**Two faces:** internally the load-bearing object is **Decision** (actionable, PR-keyed plumbing); externally the user only ever hears **Engineering Learning** ("your organization just learned something"). **Rebrand the surface, not the substrate.**

> **Resolution (vision vs. build):** Capabilities/Topics are the navigation/product layer; we do **not** hand-build a taxonomy — they emerge from `cognify` or are lightly seeded for the demo corpus. The §4 open question (does an engineer reach for a Capability, a Topic, or a Concern when they "need context"?) is settled empirically on the corpus **before** building the experience layer.

---

## 5. Functional requirements (MoSCoW)

### MUST (the MVP — the thing that wins)
- **M1. `remember` — real GitHub history, no docs.** Self-hosted Cognee ingesting **merged PRs (title/body/diff/files/author/date) + linked issues (thread + comments) + review comments**, pulled live from the GitHub API. **No ADRs, no Slack.** `cognify` synthesizes `EngineeringDecision` nodes anchored to the establishing PR, with rationale drawn from linked issues/discussion. **No markdown corpus:** the offline/demo fallback is a cached JSON snapshot of the API responses (`.sentinel/api_snapshot.json`); the demo data is *created in a real repo via the API* by `scripts/seed_demo_repo.py`. Deployable on ANY repo — including Cognee's own. *(Scoring surface — do not shrink.)*
- **M2. `recall` — multi-hop reconstruction of the lesson.** On a PR, retrieve the contradicted decision **and its WHY** (reasoning + outcome + author + date + PR/issue links) by real traversal, including the graph-only hop (incoming diff → governing decision → incident issue) that vector-alone and `#ref`-alone both miss.
- **M3. Memory Review comment (the climax artifact).** A GitHub Action triggers on PR open, runs end-to-end in <30s, posts a **natively-styled "Memory Review" card** — *What this PR changes / Why this matters / What your org currently believes (with the PR+issue evidence chain) / Memory impact + confidence* — not a list of retrieved documents. No citation → no comment.
- **M4. `forget` — human-in-the-loop supersession, PR-keyed.** An "Intentional / Supersede" reply (`/sentinel intentional`) triggers a **real `forget`**: retire the **PR-keyed** decision node, write the new learning, latest-wins. Durability via Cognee persistence + `.sentinel/retired.json` skip-list (no ADR file, no `memory/`).
- **M5. Live behavior flip.** Re-running detection after a forget returns a **different result** (the flag disappears) — detection reads live graph state, never a cached verdict. *(Requires Cognee stores to persist between before/after — verify the runner doesn't wipe them.)*
- **M6. `improve` — feedback that changes the next run.** 👍/👎 (`/sentinel noise`) stored and queryable; a 👎 **demonstrably suppresses** a similar future flag. Keyed on the drift signature (not ADR-dependent). Wire this reply path into the Action.
- **M7. Curated graph visualization** (6–8 relevant nodes, before/after states) — demo + Best-Use-of-Cognee evidence.
- **M8. ONE contradiction type, done flawlessly** (recommended: "async email chosen to cut ~600ms checkout latency after a Black Friday incident" → PR makes it sync again).
- **M9. Trust-tier gating (minimal — see §6.1).** Only **human-approved** memory drives a confident reversal flag; **machine-inferred** memory surfaces as "possible (confidence X)". `/sentinel intentional` + 👍/👎 are the human-approval signals that promote/demote via `improve()`. Approved memory is *sticky*, inferred is *fluid* (the asymmetry rule).

### SHOULD (if core is solid by Day 4)
- **S1.** Confidence threshold + "noise budget" — only surface flags above confidence; show a precision number on a real PR set ("N PRs, M flags, K confirmed").
- **S2.** Auto-drafted superseding learning when a maintainer confirms "intentional."
- **S3.** Incremental ingestion (only new PRs per Action run).
- **S4. The one-line question (see §6.2)** — when inference can't find the *why*, Sentinel asks the author/reviewer **one well-articulated question** answerable in a single line; the reply promotes the memory inferred → approved. Stretch demo beat with a kill switch; the lightweight, in-thread approval primitive (consistent with W4).

### WON'T (this hackathon — explicit cuts, each a "future work" slide)
- **W1.** ADRs / Slack / separate decision docs as inputs → **killed.** Ingestion is PR + issue + review only.
- **W2.** A `memory/` directory artifact → **killed.** Memory lives in Cognee, surfaced via the comment + graph viz. ("Two repos: src + memory" survives as narrative only.)
- **W3.** **Code ingestion** (file→capability traversal, the new-engineer face) → deferred; full-repo `cognify` is expensive and not demo-critical. Selective-only if at all.
- **W4.** **Phase-0 candidate-memory approval queue** (confidence + accept/reject UI) → the `/sentinel intentional` reply IS the approval primitive for the demo.
- **W5.** **General "is this any learning?" classifier** on the live path → the live catch is the **supersede (reversal)** case (highest-stakes, most provable). Create/refine/confirm are the product *story* + roadmap.
- **W6.** **AI-agent / MCP "ask-the-graph"** face → future-work slide (MCP keeps a Day-4 kill switch).
- **W7.** Capability/Topic auto-clustering at scale, multi-repo, multiple contradiction types → slide bullets.
- **W8.** Any ML training for `improve` → feedback-weighted lookup only.
- **W9.** Dependence on a live webhook round-trip during the demo (see §8).
- **W10.** **Proactive assumption-drift auto-firing** (surfacing stale decisions when a metric/event meets an `invalid_when` condition) → roadmap. *Live:* assumptions + invalidation conditions are stored and shown in the card/question; only the auto-detection is deferred.

### 5.1 Bootstrap — how we understand past PRs (the `remember` pipeline)
Turning a repo's history into memory is a five-step pipeline, **not a dump**:
1. **`add` → `cognify`** each PR-body / diff / linked-issue / review as typed docs → entities + typed edges.
2. **Decision filter (most important):** *not every PR is a decision.* Typo fixes / version bumps / routine fixes are noise that must **not** become memory. Decision-bearing = touches architecture/config/infra, articulates a rationale, links to an incident, or adds/removes a durable pattern. Only those → **Candidate Learnings**.
3. **Rationale reconstruction (guardrailed, §6):** mine the *why* from body + incident issue + review. No recorded why → low-confidence candidate tagged "rationale not in history" (target for the §6.2 one-line question).
4. **Compression to a Learning:** cluster related PRs/issues on one topic into a single meta-node (experience → lesson).
5. **Temporal latest-wins:** process in merge-date order so later decisions supersede earlier — reconstruct *what the org currently believes* (Cognee `TEMPORAL`).

**Two orthogonal axes:** **confidence** (how well-evidenced) vs. **provenance tier** (who stands behind it — §6.1). **Everything bootstrapped is born `inferred`** — history ≠ human ratification; it seeds traversal (SPINE-1 needs the node to exist) and feeds the candidate pool, but only *proposes* until promoted (§6.2). **Demo:** pre-seed the primary decision as approved history (an honesty-rule-compliant *input*, §8) so the WOW flag is confident.

---

## 6. The four verbs — cheapest *honest* version of each
- **remember** — real, from the repo's own GitHub history (merged PRs + diffs + linked issues + review comments). No ADRs/Slack/seeded files on the demo path.
- **recall** — real multi-hop traversal (incoming diff → governing decision → rationale issue), then LLM grounded *only* in retrieved context. The money shot; never fake.
- **forget** — retire the **PR-keyed** decision node via `cognee.forget`; `supersedes` edge + active/retired flag, latest-wins. Honest because retirement genuinely changes future recall. Durability = Cognee persistence + `.sentinel/retired.json`.
- **improve** — 👍/👎 → session feedback → `cognee.improve()` nudges `feedback_weight` (gentle `alpha=0.3`, not an erase). Honest because the next recall demonstrably shifts. Ranking model = future work.

> **The inference guardrail (non-negotiable):** inference **connects and compresses evidence that exists** (PR body + issue thread + diff); it **never invents a rationale written nowhere.** No supporting evidence → **stay silent** (or "decision recorded; rationale not found in history"). A hallucinated lesson is the fastest way to lose judge trust — this guardrail is what keeps narrowed ingestion honest.

### 6.1 Memory trust tiers — inferred vs. human-approved
Every memory carries a **provenance tier** (a node property + `feedback_weight`) and the two behave with different *authority*:
- **Machine-inferred (unconfirmed)** — extracted by `cognify`; nobody confirmed it. Ranks below approved memory; may only **propose** ("possible, 63%"), never drive a hard flag. **Fluid:** cheap to promote/demote; decays/prunes (`memify`) if never used or confirmed; cannot retire an approved memory on its own.
- **Human-approved** — a person stood behind it (answered Sentinel's question, `/sentinel intentional`, or 👍). Higher weight, surfaces first, the **only** tier allowed to drive a confident flag. **Sticky:** durable until explicitly superseded; a single 👎 must not erode it. Records *who/when* + the exact human text as the strongest evidence node.
- **Asymmetry rule:** approved = sticky, inferred = fluid. Kills noise (unconfirmed can't shout) AND prevents erosion (confirmed truth isn't automated away). **Cognee-native:** human approval is the strongest `add_feedback` → `improve()` signal, raising `feedback_weight` so recall (`feedback_influence>0`) ranks approved above inferred.

### 6.2 The one-line question — how a human promotes memory
When inference can't find the *why* (§6 guardrail), Sentinel asks the right person **one well-articulated question** answerable in a single line — the question carries the context so the answer doesn't have to (**invert the effort**).
- **Articulation template** (pinned, low temp, over the retrieved subgraph): *Evidence I found → Inference I made → the one load-bearing gap → cheap reply menu (intentional / oversight / other: …)*.
- The one-line reply resolves intent, supplies the tacit *why* in the human's words, and **promotes inferred → approved** (attributed). It is the bridge between the tiers.
- **Guardrails:** ask **rarely** (budget tighter than the flag budget); route by role (**author** = why/intent, **reviewer** = authority to supersede); **one question per PR max**; hand a hypothesis to react to, not a blank; **silence degrades gracefully** (memory stays `candidate`, re-ask later, never blocks merge); parse loosely, store verbatim.
- **Scope:** the minimal trust gating (M9) ships live; the **proactive auto-ask is a stretch beat with a kill switch** (S4). A well-articulated question is itself a one-screenshot demo asset.

### 6.3 Behavioral cases — what happens per PR (build-spec for `detect.py`)
**Default is silence.** Sentinel speaks only when durable knowledge is at stake. 3-question router: (1) decision-bearing? no → **silent**; (2) relation to memory? net-new / consistent / contradicts / invalidates-an-assumption; (3) rationale recorded? missing + high stakes → **ask one line**. Invariant: **advisory — never blocks the merge.**

| # | PR example | Decision-bearing? | What Sentinel does | Verb |
|---|---|---|---|---|
| **UC0** | Typo / formatting / dep bump | No | **Silent.** | — |
| **UC1** | Routine bug fix (`add null check`) | No | **Silent.** | — |
| **UC1b** | Bug fix carrying a lesson (`make retry idempotent — fixes #88`) | Yes | Light: drafts a **Candidate Learning** (*inferred*) | remember |
| **UC2** | New decision, **why present** (`Kafka — see #91`) | Yes | **Captures** it, **no flag** (Learning + Assumption + condition) | remember |
| **UC2b** | New decision, **why missing** (`switch to Kafka`) | Yes | **Asks one line**; candidate "rationale not in history" | remember + ask |
| **UC3** | Consistent refinement (`tune Kafka partitions`) | maybe | **Silent / confirms**; nudges confidence | improve / confirm |
| **UC4** | **Reverses an *approved* decision** (`email sync again`) | Yes — contradicts | **Asserts facts + assumption, *asks* the judgment** (detective, never a verdict) | recall → forget/improve |
| **UC4b** | Reverses an ***inferred*** decision | Yes — contradicts | **Soft proposal** ("possible — confirm?") | recall |
| **UC5** | **Invalidates an assumption** (`benchmark: send now 50ms`) | evidence | Notes assumption **at-risk** → decision may be stale | memify / forget |
| **UC6** | Reversal **similar to one already 👎'd** | Yes | **Silent** — suppressed by prior feedback | improve (suppression) |

**Cross-cutting modifiers:** (a) **trust tier → assertiveness** (approved = confident flag UC4; inferred = soft proposal UC4b — §6.1); (b) **missing rationale → ask, never fabricate** (UC2b — §6 guardrail); (c) **prior dismissal → silence** (UC6). **UC4 = detective not judge:** assert only what's certain (contradicts X + the assumption), *ask* what only the human knows (does the assumption still hold / is it intentional); the statement-to-question ratio scales with what we know. **Mental model:** **librarian** for new knowledge (UC1b–UC3), **guard** only when knowledge is contradicted (UC4–UC5), **silent** otherwise (UC0–UC1, UC6).

---

## 7. Success criteria (top-tier if 5+; losing #3 or #4 loses Best Use of Cognee)
1. Real-repo catch: ≥1 genuine reversal flagged on a repo we did **not** author, with correct citations to PR + issue.
2. Multi-hop proof: ≥1 catch needing a hop unreachable by vector similarity **and** by `#ref` link — only by graph + semantic reasoning.
3. `forget` proven on screen: before/after graph query; same PR no longer flagged after; PR-keyed decision node visibly retired.
4. `improve` proven on screen: a dismissed drift type stops surfacing after feedback.
5. A stated precision ratio on real PRs (even small N).
6. The §1 "what breaks without Cognee" sentence — every teammate says it identically.
7. One-screenshot test: the Memory Review comment alone communicates the value.
8. Reproducibility: the demo re-runs live (graph persists between before/after — verify the runner).
9. **Two-year test:** the honest answer to "what does a company now know that it didn't?" is "thousands of continuously-refined engineering lessons," never "more documents."

---

## 8. Demo (5 min) & the honesty rule
- **Beats:** Hook (the wound) → REMEMBER (the memory graph exists, built from PRs + issues — no docs) → RECALL (the catch — "this changes what your org believes about Messaging"; land it slow, 3s silence) → IMPROVE (detective not judge, 30s, compressible) → **FORGET = THE WOW** (mark intentional → graph mutates live → identical PR now silent) → Close (the positioning line). Rehearse to **4:30**.
- **The single WOW:** *same PR, opposite behavior, because memory was forgotten — shown as a before/after graph mutation.* Protect REMEMBER→RECALL→FORGET; `improve` is the cut-for-time beat.
- **Honesty rule:** pre-seed *inputs and history* (ingestion of PRs/issues, prior 👍/👎). **Never** pre-seed *outputs you claim the AI produced live* — the recall comment, the forget mutation, and the behavior flip are generated live. **Volunteer this to judges; it builds trust.** Corollary: we never claim a rationale the history doesn't contain (§6 guardrail).

---

## 9. Top risks → de-risk
- **Re-anchoring forget off ADRs breaks the WOW** → §2 sequencing rule: build + re-prove SPINE-2 on the PR-keyed path *before* deleting the ADR path; `.sentinel/retired.json` backstop.
- **SPINE-1 degrades to "GitHub API with extra steps"** → verify the graph-only hop on the new corpus (incoming diff ↔ incident issue: no `#ref`, no shared words).
- **Hallucinated rationale** → §6 inference guardrail; no evidence → silence.
- **Durability** → Cognee stores must persist between flag and re-check; verify the self-hosted runner doesn't wipe them.
- **Scope creep from the bigger vision** → the §10 cut-filter + §5 WON'T line; protect the spine above all. **Maximal rewriting is the threat to winning, not the means** — we have a working spine and full runway.
- **Live demo flakiness** → pre-staged PR + on-demand re-run + recorded honest backup; never depend on network on stage.
- **LLM nondeterminism on the climax comment** → pinned model, low temp, tight prompt over the retrieved subgraph, known-good fallback.
- **False positives** → one curated type + "detective not judge" framing + a control set of PRs it stays silent on.
- **Integration hell late** → skeleton already wired; **feature freeze after Day 4.**

---

## 10. Six-day plan (Jun 29 – Jul 5) — re-anchor + experience-layer forward
The spine is built on ADR machinery; the plan re-anchors it to PR/issue and front-loads the experience layer.
- **Day 1 — Corpus migration + lock the model + reskin the climax.** Convert demo corpus to **PRs + issues** (rationale in an incident issue, not the diff). Settle the §4 entry-point noun. Rewrite `comment.py` → **Memory Review** card. **Gate: climax comment reads as a learning story from PR+issue evidence; the graph-only hop verified.**
- **Day 2 — Re-anchor decisions + forget to PR-keyed; re-prove SPINE-2.** Decision nodes from establishing PRs; `forget` retires the PR-keyed node; `.sentinel/retired.json` backstop. **Gate: SPINE-2 re-proven on the PR-keyed path — THEN delete the ADR code path.**
- **Day 3 — Wire `improve` into the Action + confidence.** `/sentinel noise` reply path live; confidence on the card. **Gate: 👎 suppresses a similar future flag end-to-end.**
- **Day 4 — North-star dry run on a repo we didn't author + FEATURE FREEZE.** Curate graph viz (6–8 nodes, before/after). **Gate: SPINE-1 + SPINE-2 on the target repo.**
- **Day 5 — Harden + de-risk.** Pre-stage repo + PR; record backup; lock prompts/fallbacks; verify store persistence; rehearse the flip 3× clean. **Gate: demo runs clean 3× in a row.**
- **Day 6 — Presentation + buffer.** Deck (Stripe→Postgres positioning, two-year test, "no docs required" wedge, 4-verb story, graph screenshot, what-breaks-without-Cognee line, roadmap slide). Rehearse to 4:30. Jul 5 = buffer/submission.

---

## 11. The cut-filter & the one sentence that must be true
**One rule for every feature:** *Does this make the organization smarter after the merge than before the merge?* Yes → it belongs. No → cut it.

**The sentence everyone says identically:** *Remove Cognee and Sentinel breaks — because a learning is a relationship between distant, differently-worded events (an incident, a decision, an outcome) that are NOT linked by any `#ref` and share no words, so only typed graph traversal + semantic recall together can reconstruct it. Similarity search alone can't see the relationship; the GitHub API alone can't follow a link nobody wrote; a graph alone can't match "the thing we use for caching" to "Redis."*

---

## 12. Disqualifier / hygiene checklist
- [ ] **Disclose all AI tools used** (incl. Claude Code) in the submission.
- [ ] Cognee **self-hosted**, repo **public**, runs **from a clean clone** with one-command setup + README.
- [ ] Permissive **LICENSE** present (Open Source track).
- [ ] Secrets via Action secrets — **never committed.** *(The `github_pat.text` and `.pem` in the working tree must NOT ship in the public repo.)*
- [ ] Cognee is on the **live demo path** — a judge grepping for Cognee calls finds them, not stubs.
- [ ] No dependency on a competitor's platform (it's our own Action).
- [ ] All submission artifacts (demo video, repo, writeup) within the window.
