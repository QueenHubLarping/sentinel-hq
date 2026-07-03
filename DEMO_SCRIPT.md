# Sentinel — demo script (wow first, ≤3:00 tight cut · 4:30 full cut)

> Every beat below is **live on the public repo** — nothing needs to be run on stage.
> Backup plan: the same story told by scrolling the PR comment history (it's all there, timestamped).
> One-link version for judges: **https://queenhublarping.github.io/sentinel-test-repo/**

## 0:00 — OPEN ON THE WOW (30s) — screen starts on PR #22's Memory Review comment

> (no preamble — the card is already on screen)
>
> "This PR 'simplifies checkout'. Every review bot approves it. This comment is our bot
> catching that it silently **reverses a decision the team paid for on Black Friday** —
> and reconstructing the why: sync email cost ~800ms of checkout latency and real revenue.
> Here's the kicker: this PR shares **no keywords** with that incident and **links to
> nothing**. Keyword search can't find it. The GitHub API can't follow a link nobody wrote.
> Only Cognee's graph-plus-vector memory reconstructs the chain. That's Sentinel —
> institutional memory for your codebase. Let me show you the whole lifecycle."

*(For the 3:00 cut: keep beats 0:00 → RECALL-recap → FORGET → close; compress REMEMBER
into one sentence over the issues page and cut IMPROVE to one line.)*

## 0:30 — REMEMBER (45s)

Show the test repo: **8 incident issues** + **8 merged decision PRs** (auth, payments, infra,
search, webhooks, messaging…).

> "This is just a repo's normal history — no ADRs, no docs, no wiki. Sentinel ingests merged PRs
> and their linked incident issues through the GitHub API into a self-hosted Cognee knowledge
> graph. `cognify` extracts the typed edges: this PR *implements* that decision, *justified by*
> that incident. ~160 nodes from 17 documents. Zero documentation tax."

## 1:15 — RECALL: the catch (75s — land it slow)

Open **PR #22** — "Simplify checkout: send confirmation email synchronously". Scroll to the
Memory Review comment.

> "A new contributor simplifies checkout — sends email inline, deletes the queue. Looks clean.
> Every reviewer bot says LGTM."
>
> (pause on the card, 3 seconds)
>
> "Sentinel says: this PR doesn't just change code — it changes **what your organization
> believes**. It reconstructs the original lesson: email is async because synchronous send
> added ~800ms to checkout during a Black Friday incident — and that cost conversions.
> Here's the thing: **this PR shares no keywords with that incident and links to nothing.**
> Vector search can't find it. The GitHub API can't follow a link nobody wrote. Only typed
> graph traversal *plus* semantic recall — Cognee's hybrid layer — reconstructs the chain:
> incoming PR → governing decision → incident issue."

Click **the Visual Memory Recap link** in the comment → the live interactive page.

> "Every flag ships this: the diff annotated against memory, the belief card, and the evidence
> graph — press *Play the traversal* and watch the multi-hop recall happen."

## 2:30 — The numbers (20s)

Show the demo index / STRESS_REPORT.

> "We didn't demo one lucky catch. Twelve open PRs: eight genuine reversals across six
> domains — all caught with the right decision and incident cited — and four noise PRs:
> a typo fix, a dependency bump, a bugfix, a tuning PR. All silent. Including a *Celery
> version bump* sitting right next to an active Celery decision. Zero false positives."

## 2:50 — IMPROVE (30s)

Open **PR #23** → the `/sentinel noise` reply → the "Got it" confirmation → then **PR #24**
(same drift, later run): quiet.

> "Maintainers talk back. A 👎 flows through `cognee.improve()` — it down-weights the exact
> graph elements that produced the flag. PR #24 reverses the *same* decision — Sentinel now
> stays quiet about it. Feedback that visibly changes future behavior."

## 3:20 — FORGET: the WOW (50s)

Back to **PR #22**'s comment history, top to bottom:

> "Now the big one. The team decides the reversal is *right* — the provider got faster, the
> constraint changed. One reply: `/sentinel intentional`."
>
> (point at the ✅ "Learning retired" comment)
>
> "Sentinel retires the decision via `cognee.forget()` — a real graph mutation plus a durable
> ledger committed to main. And here's the proof —"
>
> (point at the re-run: same PR, **no flag**)
>
> "**The same PR, re-run: silent.** The organization remembered, then deliberately learned
> something new. Memory that updates the moment the team makes a new call — that's the
> difference between a search index and a memory."

## 4:10 — Close (20s)

> "Remove Cognee and Sentinel breaks: a learning is a relationship between distant,
> differently-worded events that share no words and no links — only typed graph traversal
> plus semantic recall together reconstruct it. Cognee is memory infrastructure; Sentinel is
> the organizational learning engine on top. Stripe is to Postgres what Sentinel is to Cognee.
> Point it at any repo — the memory is already in your history."

---

**Honesty line (say it if asked, or proactively):** the demo repo's PRs/issues are seeded
*inputs* (created through the GitHub API); every Sentinel *output* — comments, recaps, graph
mutations, the behavior flip — was generated live by the Action. AI tools used: Claude Code
(disclosed).
