# Sentinel — Product Spec

> **Sentinel is the Memory OS for software engineering. Every important engineering lesson your team learns becomes impossible to lose.**
>
> Built on Cognee. Hackathon: Cognee "Hangover Part AI" (Jun 29 – Jul 5, 2026). Track: **Best Use of Open Source** (self-host).
> Team: Chayan, Rudradeep, Abhijit.

This is a **product spec**, not a hackathon spec. It describes the whole product, then §10 draws the line at what ships live in 5 days. Where the full vision and the live-demo reality conflict, the resolution is recorded inline. This supersedes the framing in `REQUIREMENTS.md` (kept as the tactical/demo playbook); the spine discipline from that doc is carried forward here, not discarded.

**Two foundational scope decisions (locked):**
- **No ADRs, no Slack, no separate docs as inputs.** Sentinel reconstructs the *why* from what every repo already has — **merged PRs, their diffs, linked issues, review comments, and human input** — not from hand-written decision records. This makes Sentinel deployable on *any* repo and makes the "memory, not document-retrieval" claim honest.
- **No `memory/` directory.** Memory lives **in Cognee** (graph + vector) and is surfaced through the **Memory Review comment** and the **graph visualization**. We do not maintain a parallel markdown store.

---

## 0. Positioning — the one thesis everything hangs on

We are **not** building a better memory system than Cognee. We are building **the best application of Cognee.**

```
Cognee   → memory infrastructure   (remember / recall / improve / forget; graph + vector)
Sentinel → engineering intelligence (turns engineering activity into reusable organizational learning)
```

The analogy we say out loud to judges: **Stripe is to Postgres what Sentinel is to Cognee.** Stripe didn't build a database; it built payments *on* one. We don't build a memory layer; we build *organizational learning* on one. Sentinel sits exactly one semantic layer above Cognee — the cleanest possible "Best Use of Cognee" story.

**The one sentence that must be true (say it identically across the team):**
*Remove Cognee and Sentinel breaks — because a learning is a relationship between distant, differently-worded events (an incident, a decision, an outcome) that are NOT linked by any `#ref` and share no words, so only typed graph traversal + semantic recall together can reconstruct it. Similarity search alone can't see the relationship; the GitHub API alone can't follow a link that was never written; a graph alone can't match "the thing we use for caching" to "Redis."*

---

## 1. First principles — why this product exists

1. **An LLM is a stateless function.** `output = f(input)`. It has no memory. Every coding agent wakes up knowing nothing and re-reads the repo.
2. **Codebases remember *what* changed, never *why*.** `git blame` gives an author and a line, never the reasoning, the tradeoff, or the incident that forced the decision.
3. **Memory is not an archive. Memory is compression.** A one-hour meeting becomes one sentence: *"Never make email synchronous — checkout latency doubles."* If stored memory can't change future behavior, it isn't memory; it's storage.
4. **Humans recall experiences, not documents.** Ask an engineer "why async email?" and they don't think "ADR → Slack." They think *"checkout latency blew up during Black Friday, so we moved it off the request path."* The artifact is evidence; the **lesson** is the memory.
5. **Therefore the unit of organizational memory is the Engineering Learning** — a compressed, reusable lesson distilled from engineering activity, backed by evidence, that changes how the next decision gets made.

> **Memory = compression of experience into reusable lessons.** A company with 500,000 commits doesn't want 500,000 memories. It wants ~4,000 learnings — and it should not have to have written a single ADR to get them.

---

## 2. What we're building — the Organizational Learning Engine

Every important engineering event flows through one loop:

```
Engineering activity (PRs · issues · reviews) → Extract → Learning → Stored → Reused → Refined → Forgotten
```

That loop is exactly Cognee's lifecycle (`remember` / `recall` / `improve` / `forget`), applied to a single, high-value domain: **the reasoning behind a codebase — reconstructed from its own development history, with no documentation tax.**

In practice Sentinel plays three roles, and **default is silence**: a **librarian** that quietly captures new knowledge, a **guard** that speaks up *only* when knowledge is being contradicted, and **silent** for the routine majority (typos, bumps, one-line fixes). The full per-PR behavior is §8.3.

**North-star demo:** a judge watches Cognee's *own* repo receive a PR that silently reverses a past engineering decision. Sentinel doesn't say "related PRs." It says: **"This PR doesn't just change code — it changes what your organization believes about Messaging,"** and reconstructs the original lesson (reasoning + outcome + evidence) by multi-hop traversal across PRs and issues. The maintainer marks it intentional → the graph **forgets** the old learning live → **the same PR is no longer flagged.** The org remembered, then learned something new — visibly.

**The test that decides whether we built the right thing (§15):** *After two years on Sentinel, does a company "have more documents" (we lose) or "thousands of continuously-refined engineering lessons every engineer and AI agent can instantly apply" (we win)?*

---

## 3. Two faces — internal substrate vs. external experience

This separation is non-negotiable and resolves most of our design tension.

| | Internal (the graph / the code) | External (what the user experiences) |
|---|---|---|
| Core object | **Decision** (actionable), plus Assumption, Outcome, Evidence | **Engineering Learning** — "Your organization just learned something" |
| Anchor / identity | **The establishing PR** — decision id derived deterministically from the PR number (fixed-namespace UUID) | (invisible to the user) |
| Operation | `cognee.remember / recall / forget / improve` over PR/issue history | "Sentinel created / refined / superseded / confirmed a learning" |
| Vocabulary in code | `Decision`, `EngineeringDecision`, PR-keyed ids | "Engineering Learning", "Memory Review", "Memory Commit" |

**Rule: rebrand the surface, not the substrate.** Decisions stay the actionable core object internally (a learning is often the *result* of one or more decisions + outcomes). Users only ever hear "learning." *(Note: the identity anchor moves from ADR-filename → establishing-PR-number; everything else about the substrate is unchanged.)*

---

## 4. The knowledge model — exactly two conceptual layers

Do **not** over-normalize. The graph mirrors **how engineers mentally model the system, not the repository directory tree.**

**Layer 1 — Capabilities (the navigation entry point).** Long-lived, cross-cutting concerns, *not* tied to directories: `Messaging`, `Authentication`, `Payments`, `Checkout`, `Search`, `Observability`. This is what a user picks first: *"Show me everything about Messaging."* Under a capability sit **Topics** — coherent engineering problems (`Retry Policy`, `Async Email`, `Cache Invalidation`).

**Layer 2 — Knowledge objects (one shared ontology, every domain).** `Decision`, `Assumption`, `Experiment`, `Incident`, `Outcome` → which compress into a **Learning**.

**Assumptions are first-class — memory is conditional, not absolute.** A decision is never absolute; it is `Decision **because** Assumption holds`. So we store not just the assumption but **the conditions under which it stops being true.** An `Assumption` node carries:
- **statement** — the conditional premise (e.g., *"synchronous email send adds ~600ms, exceeding checkout's latency budget"*).
- **invalidation_conditions[]** — the case(s) it stops holding under, thresholded *or* qualitative (e.g., *"email-send latency drops materially"*, *"email leaves the checkout critical path"*, *"the latency budget is relaxed"*).
- **status** — `holding | at-risk | invalidated`.
- inherits **confidence + provenance tier** (§8.1) — so a human can ratify a condition via the one-line question.

This turns recall from *retrospective* ("you're reverting a decision") into *conditional* ("this is safe **only if** X is still true — is it?"), gives a **principled `forget` trigger** (a confirmed-met condition makes the decisions resting on it legitimate supersession candidates), and enables **proactive assumption-drift** (roadmap, §10). **Guardrail (§8):** invalidation conditions are inferences too — never fabricate a numeric threshold the history doesn't state; store it qualitatively and mark it inferred.

**Evidence (supports memory, never *is* memory).** `PR` (body + diff), `Issue` (thread + comments), `Review comment`, `Commit`, `Benchmark`. **Evidence never becomes a memory; it backs one.** This distinction is what keeps the graph from degenerating into a document pile. *(Rationale text is mined from issue threads / PR discussion — never invented from the diff; see §8 guardrail.)*

```
Capability ─┬─ Topic ─┬─ Decision ─┬─ rests_on   → Assumption ─┬─ invalid_when → Condition
            │         │            │                           └─ supported_by → Evidence (benchmark · incident · PR)
            │         │            ├─ supported_by → Evidence (PR diff/body · Issue thread · review · commit)
            │         │            └─ led_to       → Outcome ── distills_to → Learning
            │         └─ Topic ...
            └─ Topic ...
```

> **Resolution (vision vs. build):** Capabilities/Topics are the *navigation and product* layer. We do **not** hand-build a taxonomy. They emerge from `cognify` (or are lightly seeded for the demo corpus). Internally, **Decision remains the load-bearing object**, now anchored to its establishing PR.

**Open question we answer empirically, not in schema (Day-1 decision):** when an engineer thinks *"I need context,"* what noun do they reach for — a Capability ("Messaging"), a Topic ("async email"), or a Concern ("checkout latency")? Whichever wins becomes the default entry point. Getting this right matters more than any node type, because it decides whether the product thinks like the user or forces the user to think like the graph.

---

## 5. The product lifecycle — 6 phases, each mapped to a Cognee verb

### Phase 0 — Bootstrap Memory  *(`remember`)*
One-time import of real history from the GitHub API — **merged PRs** (title, body = the "why", diff, files, author, merge date), **linked issues** (thread + comments — where incidents and rationale live), and **review comments** — turned into memory by a five-step **understanding pipeline** (not a dump):

1. **`add` → `cognify`** — each PR-body, diff, linked issue, and review thread is added as a typed document; `cognify` extracts entities + typed edges (component/capability touched, what changed, what it references).
2. **The decision filter (the most important step).** *Not every PR is a decision.* Typo fixes, version bumps, and routine bug fixes are **noise that must not become memory.** A PR is decision-bearing only if it touches architecture/config/infra (not just a value), articulates a rationale, links to an incident, or introduces/removes a durable pattern (async→sync, library swap). Only those become **Candidate Learnings**; the rest stay as raw evidence at most.
3. **Rationale reconstruction (guardrailed, §8).** Mine the *why* from PR body + linked incident issue + review discussion. Found → confident candidate. Decision visible in the diff but **no recorded why** → low-confidence candidate tagged *"rationale not in history"* — the exact target for a later one-line question (§8.2).
4. **Compression to a Learning.** Cluster related PRs/issues on one topic into a single meta-node: PR #42 (introduce async email) + issue #91 (the incident) + PR #58 (queue tuning) → one Learning: *"email is async to protect checkout latency."* Experience → lesson.
5. **Temporal ordering / latest-wins.** Process PRs in merge-date order so a later decision **supersedes** an earlier one — reconstructing *what the org currently believes*, not a pile of contradictions. (Cognee's `TEMPORAL` extraction is built for this.)

**Two orthogonal scores fall out** — and keeping them separate is the crux:
- **Confidence** — *how well-evidenced* (rises with convergence: body + issue + reviewers agreeing > a lone diff).
- **Provenance tier** — *who stands behind it* (§8.1).

**Everything bootstrapped is born `inferred`** (§8.1), no matter how confident — history alone is not human ratification. So it's the *fluid* tier: it can provide context and **propose** ("possible — inferred from PR #42"), but does not drive a confident flag on its own (a safety property — `cognify` will occasionally mis-read a hack as a "decision"). It is **not idle**: it seeds the graph so multi-hop traversal works at all (SPINE-1 needs the historical decision node to exist) and is the candidate pool the one-line question draws from. Promotion to **approved** happens *lazily, when a candidate first becomes relevant* (§8.2) — you never bulk-approve 500 candidates upfront.

Works on *any* repo — including Cognee's — with **zero documentation prerequisite**.

> **Demo-scope note:** for a *confident* reversal WOW (not a soft "possible"), pre-seed the primary decision (async email) as **human-approved history** — allowed under the honesty rule (§11): it's a pre-seeded *input/history*, not a claimed-live output. Bootstrap then shows the *inferred* tier on the surrounding candidates, the confident flag fires off the *approved* decision, and FORGET retires it — both tiers demonstrated in one honest run.

### Phase 1 — Daily Development  *(no-op)*
Developers work normally. No docs, no forms, no ADRs. Trivially true — and the point: **zero adoption tax.**

### Phase 2 — PR Opened  *(`recall` + judge)*
Sentinel analyzes diff + linked issue + PR description against the graph and asks: **"Does this PR create, refine, supersede, or confirm long-lived organizational knowledge?"**
- **No → stay silent.** Noise kills products. No citation, no comment.
- **Yes → draft a Possible Learning** (title, why, tradeoffs, assumptions, evidence, affected capability), grounded *only* in retrieved evidence (§8 guardrail).

### Phase 3 — Review  *(the differentiator)*
The reviewer never sees "20 retrieved documents." They see a **Memory Review** card:

```
🧠 Memory Review — Messaging

What this PR changes
  Moves checkout email delivery from the async queue back to synchronous send.

Why this matters
  This supersedes an active architectural learning.

What your organization currently believes
  "Email delivery is async because synchronous send added ~600ms to checkout
   latency during a Black Friday incident — and that cost conversions."
  Reconstructed via:  PR #42 (made it async)  →  Issue #91 (the latency incident)
  (no shared keywords, no #ref from this PR — recovered by graph + semantic reasoning)

Memory impact
  ⚠️  This PR would supersede that learning. Confidence in the current belief: 92%.
```

The reviewer thinks *"I understand,"* not *"I found documents."*

### Phase 4 — Merge → Memory Commit  *(`remember` / `forget`)*
The merge updates the **Cognee memory**, not a parallel folder. It writes/updates an **Engineering Learning** in the graph: `Learning · Decision · Evidence · Reviewer · Confidence · Supersedes · Affected capability`. Every merge does exactly one of four things: **creates, refines, supersedes, or confirms** a learning. (The "two repositories: src + memory" framing is a *roadmap narrative* — not a built artifact this hackathon.)

### Phase 5 — Future recall  *(`recall`)*
Months later someone touches the same subsystem. Sentinel doesn't grep documents — it **reconstructs the lesson**: `Experience → Decision → Outcome → Lesson → this PR`. A new engineer opens a file and gets an **Engineering Memory** (one story, one minute) instead of `git blame`. *(The file-open surface is a roadmap face; the live product surfaces the lesson on the PR.)*

### Phase 6 — Memory Evolution  *(`forget` + `improve`)*
Memory is adaptive, not static.
- *"This decision is obsolete"* → **`forget`**: the PR-keyed decision node is **superseded, not deleted** (`Old → superseded → New`); future recall changes. Durability rests on Cognee's persistent stores (§8).
- 👍 → **`improve`**: confidence rises, the learning ranks higher.
- 👎 → **`improve`**: the learning is down-weighted; that drift type stops surfacing. Nothing is erased — the weights live on the graph and feed Cognee's own triplet ranker.

---

## 6. End-user experiences (the four personas — optimize for these)

- **Developer** — never writes docs. Occasionally spends 10s confirming *"Sentinel understood this correctly."*
- **Reviewer** — never searches Slack/Confluence, never asks "why?". The Memory Review answers before they ask.
- **New engineer** — opens any file, gets the Engineering Memory (one story) instead of `git blame`. *(Roadmap face.)*
- **AI agent (Claude Code / Cursor / Codex)** — queries organizational memory instead of re-reading the repo. Precisely the problem Cognee exists to solve, surfaced through Sentinel.

---

## 7. Where memory lives — in Cognee, not in files

**There is no `memory/` directory.** Memory is the Cognee graph + vector store. It is surfaced to humans through exactly two windows:
- **The Memory Review comment** on the PR (the climax artifact, the one-screenshot test).
- **The curated graph visualization** (before/after a forget).

> **Why this is the stronger choice (not just the simpler one):** a markdown `memory/` folder would invite the question *"if the memory is just files, what do you need Cognee for?"* Keeping memory in Cognee — reconstructed live, mutated by `forget`/`improve`, shown in the graph — makes Cognee load-bearing and visible. **Durability of a forget comes from Cognee's own persistent stores** (graph/vector/relational files), backed by a small non-user-facing `.sentinel/retired.json` ledger so a retired decision is skipped on re-ingest even if stores are rebuilt. No hand-maintained markdown, no desync between "what we display" and "what we reason over."

---

## 8. The four Cognee verbs — honest, minimal, real

Judges will sniff a fake. Each verb is real but minimal:

- **remember** — real, from the repo's own GitHub history: **merged PRs (body + diff) + linked issues + review comments**, pulled from the GitHub API. No ADRs, no Slack, **no markdown corpus**. The offline/demo fallback is a cached JSON snapshot of the API responses (`.sentinel/api_snapshot.json`); demo data is *created in a real repo via the API* (`scripts/seed_demo_repo.py`). This is the scoring surface; do not shrink it.
- **recall** — real multi-hop traversal: *incoming PR diff → (semantic + graph) → governing Decision → justified_by rationale → evidenced_by the incident issue.* Then LLM grounded *only* in retrieved context. The money shot. Never fake it.
- **forget** — retire the **PR-keyed** decision node via `cognee.forget(data_id=…)`; `supersedes` edge + active/retired flag, latest-wins; write the new learning, retire the old (kept for history, excluded from active recall). Honest because retirement genuinely changes future recall. Durability = Cognee persistence + the `.sentinel/retired.json` skip-list.
- **improve** — 👍/👎 → session feedback → `cognee.improve()` nudges `feedback_weight` (gentle `alpha=0.3`, not an erase). Keyed on the drift signature (never ADR-dependent). Honest because the next recall demonstrably shifts. Any ranking model = future work.

> **The inference guardrail (the line that keeps narrowed ingestion honest):** inference may **connect and compress evidence that exists** (PR body + issue thread + diff) into a lesson. It may **never invent a rationale written nowhere.** No supporting evidence → **stay silent**, or state *"decision recorded; rationale not found in history"* — never a confident fabricated "why." A hallucinated lesson is the single fastest way to lose judge trust.

---

## 8.1 Memory trust tiers — inferred vs. human-approved

Every memory carries a **provenance tier** (a node property + `feedback_weight`), and the two tiers behave with different *authority* — this is what makes "memory" trustworthy rather than a pile of guesses:

- **Machine-inferred (unconfirmed)** — extracted by `cognify` from PR/issue text; nobody confirmed it. Lower weight, ranks below approved memory. May only **propose** ("Possible learning, 63% — confirm?"), never assert or drive a hard flag. **Fluid:** cheap to promote/demote; decays/prunes (`memify`) if never used or confirmed. May *suggest* a supersession but cannot retire an approved memory on its own.
- **Human-approved** — a person stood behind it: answered Sentinel's question in the PR thread, ran `/sentinel intentional`, or 👍'd a flag. Higher `feedback_weight`, surfaces first, and is the **only** tier allowed to drive a confident reversal flag. **Sticky:** durable until explicitly superseded; a single drive-by 👎 must not erode it. Records *who* approved, *when*, and the exact human text as the strongest evidence node (a direct assertion, not a reconstruction).

> **The asymmetry rule (the point):** approved memory is *sticky*, inferred memory is *fluid*. This simultaneously kills noise (unconfirmed memory can't shout) and prevents erosion (confirmed truth isn't automated away).

**Cognee-native, not bolted on:** both tiers are the *same graph nodes*; human approval is the strongest positive feedback signal, fed via `cognee.session.add_feedback` → `improve()`, raising the weight so recall (`feedback_influence > 0`) ranks approved above inferred — Cognee's critic-guided reweighting used exactly as designed.

---

## 8.2 The one-line question — how a human promotes memory

When inference hits the guardrail wall (§8: *"rationale not in history"*), Sentinel doesn't stay silent forever — it **asks the right person one well-articulated question** whose answer fits in a single line. The question carries all the context so the answer doesn't have to (**invert the effort**: Sentinel does the reasoning; the human supplies only the one thing a machine can't manufacture — ground-truth intent).

**Articulation template** (pin the generation, low temp, over the retrieved subgraph):
> *Evidence I found → Inference I made → **the one load-bearing gap** → a cheap reply menu (intentional / oversight / other: …).*

Example: *"This makes checkout email synchronous again. I traced it to the async-email decision (PR #42), which I believe cut ~600ms latency during a Black Friday incident. One line, @author: intentional (new constraint) or oversight — and if intentional, what changed?"*

The one-line reply does three jobs at once: resolves intent, supplies the tacit *why* in the human's own words, and **promotes the memory inferred → approved** (attributed, dated). It is the bridge between the two tiers.

**Guardrails:**
- **Ask rarely** — only when a real decision is at stake, the gap is load-bearing, and confidence sits in the uncertain band. The question budget is *tighter* than the flag budget; one "fill out this form" ruins trust.
- **Route by role** — the **author** for *why/intent*; the **reviewer** for *authority to supersede*.
- **One question per PR, max** — spend the interruption on the single highest-leverage unknown.
- **Hand a hypothesis to react to, not a blank** — people correct a draft far faster than they author one.
- **Silence degrades gracefully** — no answer → memory stays `candidate` (can't assert); re-ask on the next related PR; never blocks the merge.
- **Parse loosely, store verbatim** — accept yes/no/free-line; keep the exact human text as the evidence node.

**Bonus:** a well-articulated question is itself the **one-screenshot demo asset** — it communicates the product *before anyone answers*.

> **Scope (live vs. stretch):** the *minimal* trust-tier behavior ships live — inferred surfaces as "possible (confidence X)"; `/sentinel intentional` + 👍/👎 promote/demote via `improve()`; only approved memory drives the confident flag. The **auto-asked one-line question is a stretch demo beat with a kill switch**, not a spine dependency.

---

## 8.3 Behavioral cases — what happens per PR (operationalizes Phases 2–4; build-spec for `detect.py`)

**The one rule: default is silence.** Most PRs do *nothing* — Sentinel speaks only when **durable engineering knowledge is at stake.** Every PR runs a 3-question router:
1. **Decision-bearing?** (the decision filter) — no → **silent.**
2. **Relation to existing memory?** — net-new / consistent / contradicts / invalidates-an-assumption.
3. **Rationale recorded?** — missing + high stakes → **ask one line.**

Invariant across **all** cases: **Sentinel is advisory — it never blocks the merge.**

| # | PR example | Decision-bearing? | What Sentinel does | Memory effect | Verb |
|---|---|---|---|---|---|
| **UC0** | Typo / formatting / dependency bump | No | **Silent.** No comment. | none (raw commit at most) | — |
| **UC1** | Routine bug fix (`add null check`) | No | **Silent.** | none | — |
| **UC1b** | Bug fix carrying a lesson (`make retry idempotent — fixes #88`) | Yes (links incident, changes a pattern) | Light: drafts a **Candidate Learning** ("possible lesson: retries need idempotency") | new candidate Learning (*inferred*) | remember |
| **UC2** | New decision, **why present** (`Kafka — see #91, RabbitMQ collapsed`) | Yes | **Captures** it ("📝 recorded a learning"), **no flag** (nothing's wrong) | Learning + Assumption + invalidation condition (*inferred*) | remember |
| **UC2b** | New decision, **why missing** (`switch to Kafka`, no rationale) | Yes | **Asks one line** ("betting on traffic > X?") | candidate tagged *"rationale not in history"*; promoted on answer | remember + ask |
| **UC3** | Consistent refinement (`tune Kafka partitions`) | maybe | **Silent / confirms**; nudges confidence up | refines existing Learning | improve / confirm |
| **UC4** | **Reverses an *approved* decision** (`make email sync again`) | Yes — contradicts | **Asserts the facts + the assumption, *asks* the judgment** (detective, never a verdict) | `/intentional`→ forget; `👎`→ improve | recall → forget/improve |
| **UC4b** | Reverses an ***inferred* (unconfirmed)** decision | Yes — contradicts | **Soft proposal** ("possible — I inferred this from PR #42; confirm?") | promote or retire per human | recall |
| **UC5** | **Invalidates an assumption** (`benchmark: email send now 50ms`) | evidence | Notes assumption **at-risk** → "the async-email decision may be worth revisiting" | assumption.status → at-risk; forget candidate | memify / forget |
| **UC6** | Reversal **similar to one already 👎'd** (`app-level rate-limit` again) | Yes | **Silent** — suppressed by prior feedback | none | improve (suppression) |

**Cross-cutting modifiers (they reshape the cases above):**
- **Trust tier → assertiveness.** Same reversal PR behaves differently by *what it contradicts*: **approved** → confident flag (UC4); **inferred** → soft proposal (UC4b). Approved is sticky, inferred is fluid (§8.1).
- **Missing rationale → ask, never fabricate.** Any decision-bearing PR whose *why* isn't in the history triggers the one-line question (UC2b), not a made-up reason (the §8 guardrail).
- **Prior dismissal → silence.** A drift type a maintainer 👎'd stops surfacing (UC6) — the feedback loop changed future behavior.

**UC4 detail — detective, not judge.** We *assert* only what we're certain of (this contradicts decision X; here's the original why + the **assumption** it rests on) and *ask* what only the human knows (is the assumption still true / is this intentional). We **never** declare "you're wrong." The **statement-to-question ratio scales with what we know**: know a lot → statement-led + question (UC4); know little → question-led (UC2b); know nothing durable → silent (UC0).

**The mental model:** Sentinel is a **librarian** for new knowledge (UC1b–UC3), a **guard** only when knowledge is being contradicted (UC4–UC5), and **silent** for everything else (UC0–UC1, UC6).

---

## 9. What wins — the non-negotiable spine (build/protect FIRST)

"Best Use of Cognee" is won by proving two things **on screen**, before any polish:

- **SPINE-1 — Real multi-hop recall only the graph enables.** ≥1 flag where the reversed learning connects to its rationale through a hop that is recoverable **neither by vector similarity (no shared words) nor by following an explicit `#ref` link** — only by graph + semantic reasoning. The discriminating chain: the **incoming PR diff** has no lexical overlap with, and no link to, the **incident issue** that holds the rationale; Sentinel still connects them through the governing Decision. We must be able to say: *"vector-only returns nothing; the GitHub API can't follow a link nobody wrote; the typed `supersedes`/`justified_by` edges + semantic recall are what make this correct."*
- **SPINE-2 — `forget` and `improve` as visible graph mutations.** Show graph state (query + viz) **before and after** a supersession (PR-keyed decision node retired / edge re-pointed) and after a 👎 (a drift type drops below threshold and stops surfacing). Behavior change is an **inspectable before/after diff, not narrated.**

If we can't demo SPINE-1 and SPINE-2, polish doesn't matter. **Verify the graph-only hop empirically on the new PR/issue corpus** — meeting "≥2 source types" (PR + issue) is trivial; holding the *spirit* (a hop no `#ref` and no shared word can make) is the bar.

> **Sequencing rule (protects the WOW):** SPINE-2 is currently proven on ADR-keyed machinery. **Build the PR/issue-keyed decision + forget and re-prove SPINE-2 on it BEFORE deleting the ADR code path.** Never remove working substrate before the replacement is proven, 5 days out.

---

## 10. The 5-day cut — what ships LIVE vs. what is roadmap

The full product is §0–§9. The demo ships a disciplined subset. **The dividing rule:** anything on the *live demo path* must be generated live and survive a judge grepping for Cognee calls; everything else is a clearly-labeled "future work" slide.

**Ships live (the spine + the new skin):**
- `remember`: live **PR + linked-issue** ingestion into self-hosted Cognee (real history, no ADRs/Slack). ⚠️ ingestion re-pointed off ADR/Slack onto PR/issue.
- `recall`: multi-hop reconstruction of the lesson, with the graph-only hop (SPINE-1). ✅ traversal exists; verify the hop on the new corpus.
- **Phase 3 Memory Review comment** — the climax artifact. ⚠️ **copy rewrite of `comment.py`** (highest-value new work); cites PR + issue evidence.
- `forget` flips behavior live: mark intentional → PR-keyed decision retired → graph mutates → same PR no longer flagged (SPINE-2). ⚠️ **re-anchor off ADRs; re-prove before deleting old path.**
- `improve`: 👎 suppresses a similar future flag (SPINE-2). ✅ exists; wire the `/sentinel noise` reply into the Action.
- **Trust-tier gating (minimal, §8.1):** only human-approved memory drives a confident flag; machine-inferred surfaces as "possible (confidence X)"; `/sentinel intentional` + 👍/👎 promote/demote via `improve()`. ⚠️ small new gating layer.

**Detection scope on the live path — resolution:** the product *story* is "detects create / refine / supersede / confirm." The **flagship live catch is the supersede (reversal) case** — highest-stakes, most provable, highest precision. We do **not** ship a general "is this any learning?" classifier on the live path; generalizing adds false positives judges will probe.

**Roadmap (slides, not demo code), each clearly labeled:**
- Phase 0 **candidate-memory approval queue** with confidence + accept/reject UI. **The approval primitive for the demo is the existing `/sentinel intentional` reply**, reframed as "approve / supersede a learning." No new queue surface to build or fake.
- **Code ingestion** (file→capability traversal, the new-engineer face) — deferred; full-repo `cognify` is expensive and not demo-critical. Selective-only if at all.
- The "two repositories (src + memory)" framing — narrative/slide only; no `memory/` artifact built.
- AI-agent / MCP "ask-the-graph" face → future-work slide (MCP keeps a Day-4 kill switch).
- **The auto-asked one-line question (§8.2)** → stretch demo beat with a kill switch; the minimal trust-tier gating ships, the proactive ask does not block the spine.
- **Proactive assumption-drift (§4)** → when new evidence matches an `invalid_when` condition, surface *"assumption A may now be invalid → decisions X, Y are worth revisiting"* with **nobody touching that code** — the predictive-memory wow. Needs a metric/event source → roadmap slide + stretch. *(Live: assumptions + invalidation conditions are stored and shown in the card/question; only the auto-firing is deferred.)*
- Capability/Topic auto-clustering at scale, multi-repo, general contradiction types.

---

## 11. Demo script (5 min) + the honesty rule

**Beats:** Hook (the wound: code remembers *what*, never *why*) → **REMEMBER** (the memory graph exists, built from PRs + issues — no docs required) → **RECALL** (the catch — "this changes what your org believes about Messaging"; land it slow, 3s silence) → **IMPROVE** (detective, not judge; 30s, compressible) → **FORGET = THE WOW** (mark intentional → graph mutates live → identical PR now silent) → Close (the §0 positioning line). Rehearse to **4:30**.

**The single WOW:** *same PR, opposite behavior, because memory was forgotten — shown as a before/after graph mutation.*

**Honesty rule (live vs. seeded):** pre-seed *inputs and history* (ingestion of PRs/issues, prior 👍/👎). **Never** pre-seed *the outputs you claim the AI produced live* — the recall comment, the forget mutation, and the behavior flip are all generated live. **Volunteer this distinction to judges; it builds trust.** Corollary: the inference guardrail (§8) means we also never claim a rationale the history doesn't contain.

---

## 12. Success criteria (top-tier if 5+; losing #3 or #4 loses Best Use of Cognee)

1. Real-repo catch: ≥1 genuine reversal flagged on a repo we did **not** author, with correct citations to PR + issue.
2. Multi-hop proof: ≥1 catch needing a hop unreachable by vector similarity **and** by `#ref` link — only by graph + semantic reasoning.
3. `forget` proven on screen: before/after graph query; same PR no longer flagged after; PR-keyed decision node visibly retired.
4. `improve` proven on screen: a dismissed drift type stops surfacing after feedback.
5. A stated precision ratio on real PRs (even small N): "N PRs, M flags, K confirmed."
6. The §0 "what breaks without Cognee" sentence — every teammate says it identically.
7. One-screenshot test: the Memory Review comment alone communicates the value.
8. Reproducibility: the demo re-runs live (graph persists between before/after — verify the runner doesn't wipe Cognee's stores).
9. **Two-year test:** the honest answer to "what does a company now know that it didn't?" is "thousands of continuously-refined engineering lessons," never "more documents."

---

## 13. Top risks → de-risk

- **Re-anchoring forget off ADRs breaks the WOW** → §9 sequencing rule: build + re-prove SPINE-2 on the PR-keyed path *before* deleting the ADR path; keep `.sentinel/retired.json` as the durability backstop.
- **SPINE-1 degrades to "GitHub API with extra steps"** → verify the graph-only hop on the new corpus (incoming diff ↔ incident issue with no `#ref`, no shared words).
- **Hallucinated rationale** → the §8 inference guardrail; no evidence → silence.
- **Durability** → Cognee stores must persist between flag and re-check; verify the self-hosted runner doesn't wipe them; `.sentinel/retired.json` backstop.
- **Scope creep from the bigger vision** → the §15 cut-filter + §10 live/roadmap line; protect REMEMBER→RECALL→FORGET above all.
- **Live demo flakiness** → pre-staged PR + on-demand re-run + recorded honest backup; never depend on network on stage.
- **LLM nondeterminism on the climax comment** → pinned model, low temp, tight prompt over the retrieved subgraph, known-good fallback.
- **False positives** → one curated contradiction type + "detective not judge" framing + a control set of PRs it stays silent on.
- **Integration hell late** → end-to-end skeleton already wired; **feature freeze after Day 4.**

---

## 14. Six-day plan (Jun 29 – Jul 5)

The spine (remember/recall/forget/improve, SPINE-1/2) is already built on ADR machinery. The plan re-anchors it to PR/issue and front-loads the experience layer the new positioning demands.

- **Day 1 — Corpus migration + lock the model + reskin the climax.** Convert the demo corpus to **PRs + issues** (rationale lives in an incident issue, not the diff). Answer the §4 entry-point question. Rewrite `comment.py` into the **Memory Review** card. **Gate: the climax comment reads as a learning story from PR+issue evidence; the graph-only hop is verified.**
- **Day 2 — Re-anchor decisions + forget to PR-keyed; re-prove SPINE-2.** Synthesize Decision nodes from establishing PRs; `forget` retires the PR-keyed node; `.sentinel/retired.json` backstop. **Gate: SPINE-2 re-proven on the PR-keyed path — THEN delete the ADR code path.**
- **Day 3 — Wire `improve` into the Action + confidence surfacing.** `/sentinel noise` reply path live; confidence on the card. **Gate: 👎 suppresses a similar future flag end-to-end.**
- **Day 4 — North-star dry run on a repo we didn't author + FEATURE FREEZE.** Curate the graph viz (6–8 nodes, before/after). **Gate: SPINE-1 + SPINE-2 on the target repo.**
- **Day 5 — Harden + de-risk.** Pre-stage repo + PR; record honest backup; lock prompts/fallbacks; verify store persistence; rehearse the flip 3× clean. **Gate: demo runs clean 3× in a row.**
- **Day 6 — Presentation + buffer.** Deck (Stripe→Postgres positioning, the §2 two-year test, "no docs required" wedge, 4-verb story, graph screenshot, what-breaks-without-Cognee line, roadmap slide). Rehearse to 4:30. Jul 5 = buffer/submission.

---

## 15. The cut-filter + the line that must be true

**One rule for every feature for the rest of the hackathon:**

> **Does this make the organization smarter after the merge than it was before the merge?**
> Yes → it belongs. No → cut it.

**The two-year test (the product's reason to exist):** after two years on Sentinel, the honest answer to *"what does this company now know that it didn't?"* must be **"thousands of continuously-refined engineering lessons every engineer and AI agent can instantly apply"** — never "more documents." If a feature doesn't move that answer, it's noise.

---

## 16. Disqualifier / hygiene checklist

- [ ] **Disclose all AI tools used** (incl. Claude Code) in the submission — rules require it.
- [ ] Cognee **self-hosted**, repo **public**, runs **from a clean clone** with one-command setup + README.
- [ ] Permissive **LICENSE** present (Open Source track).
- [ ] Secrets (GitHub token, LLM keys) via Action secrets — **never committed.** *(Note: `github_pat.text` and the `.pem` in the working tree must not ship in the public repo.)*
- [ ] Cognee is on the **live demo path** — a judge grepping for Cognee calls finds them, not stubs.
- [ ] No dependency on a competitor's platform (it's our own Action).
- [ ] All submission artifacts (demo video, repo, writeup) within the window.
