# Process lessons

Things we learned the hard way, captured here so a compacted session or a fresh agent inherits them. Append entries with a date and a one-paragraph context. Don't rewrite history; correct it forward.

---

## 2026-05-22: undersize PRs fragment review

We shipped 15+ PRs in two sessions where most were single-file edits. PR #10 was superseded by PR #11 the same day. PR #8 was a one-line `grace_period` bump that could have ridden inside any of the other Fly-config-touching PRs. Result: the operator felt overwhelmed by the review queue and lost track of which PR did what.

**Rule:** Batch related work into one PR by default. Single-purpose PRs are for genuinely independent fixes only. PR #15 (5 social MCPs + 2 skills + entrypoint + tests + SOUL.md ladder, one shot) is the right scope template.

## 2026-05-22: write plan docs before implementing non-trivial work

Most of our work has been "agent writes inline plan in chat, operator says go, agent implements." That's fine for small fixes but it inverts the right ratio for substantial work. The article-from-the-thread (advice from teams running coding agents at scale): spend MOST time on plan docs, iterate until extremely good, then implement against the plan.

**Rule:** Anything matching the "When" criteria in `docs/plans/README.md` gets a plan doc first. Implementation follows the plan exactly; deviations require editing the plan first.

## 2026-05-22: adversarial review before declaring done

Agent has been self-reviewing PRs. Stop-hook catches "claimed without verification" but doesn't catch "shipped something subtly wrong." A fresh read-only subagent with no shared context can catch what the implementer's own pattern-matching missed.

**Rule:** Before opening a PR, spawn a fresh read-only subagent that reads the plan doc + diff and returns gaps or over-engineering. PR opens after review comes back clean. Cost: a few minutes per PR. Benefit: avoid the "looks right to me" failure mode.

## 2026-05-22: verification-first task descriptions

Past tasks (#51-#62) had vague descriptions and no "how to verify" or "proof notes" sections. Bar should be: if satisfied as written, you'd trust the result.

**Rule:** Every task description includes: (1) what to do, (2) how to verify, (3) proof notes once done. Existing tasks #56 and #62 were retro-upgraded to this format. New tasks follow the template from creation.

## 2026-05-22: OpenGateway "free" status changes; verify before claiming

OpenGateway was probed open with no auth on 2026-05-18 and we set it as default in PR #7 / config.yaml. On 2026-05-22 the same endpoint returned HTTP 401 "API key required" with no warning. Our config silently broke for any new deploy until PR #11 demoted it.

**Rule:** When a provider's auth model is not clearly documented, do NOT make it the default. List it as a switchable alternative with the date the auth model was last verified. Re-probe before each release.

## 2026-05-22: agent autonomous-ness has limits

When the operator said "be as autonomous as possible," we interpreted that as "ship as many PRs as possible." That created the overwhelm in the first lesson above. Autonomy is about not asking permission per atomic step, not about maximizing throughput.

**Rule:** Stop adding PRs to the queue when there are already 5+ open. Pause, let the operator catch up, ask if they want more or want to merge what's there.

## 2026-05-22: "fully decentralized" claims often mean "default node"

GitLawb was wired as "decentralized git network" with the implicit assumption of self-sovereign nodes. In practice every agent we provisioned pointed at the default `node.gitlawb.com` because no operator was self-hosting. That's fine for v0 but the README should not promise more than the implementation delivers.

**Rule:** Document the actual default network topology, not the aspirational one. "Decentralization-capable" is different from "decentralized in practice today."

---

## How to add a lesson

When a corrected mistake happens (operator pushback, surprise behavior, broken assumption), append a new dated section here with:

1. One short description of what went wrong (1-2 sentences)
2. Context: why it happened (1 paragraph)
3. The forward-going rule

Lessons stay in the order they were learned. Don't refactor or "improve" the prose later; the verbatim record is what makes the file trustworthy.
