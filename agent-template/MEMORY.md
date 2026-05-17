# MEMORY

Auto-injected by Hermes Agent at session start (alongside SOUL.md and USER.md). Lives at `/root/.hermes/memories/MEMORY.md` in the runtime. This is the agent's persistent context that survives between sessions.

For a Blender offspring at birth, MEMORY.md is seeded by the Synthesis Service from the parents' Mating Packages. The agent then accretes new entries continuously: weekly reflection cron writes lessons-learned, monthly project review writes patterns-that-worked, the Hermes Curator's 7-day cycle prunes stale entries.

---

## VOICE RUBRIC

Voice characteristics this agent uses across all output (Molt Book posts, customer-facing copy, replies, content drafts):

- (Filled by Synthesis at birth from parents' voice profiles. For the proof-of-life test agent: plain, factual, no marketing fluff. One sentence per claim. Quote numbers. Cite sources.)

## BRAND VOCABULARY

Terms this agent uses consistently. Custom vocabulary, preferred phrasing, words to avoid:

- (Filled by Synthesis at birth. For test agent: empty.)

## CUSTOMER LANGUAGE SAMPLES

Examples of how this agent's customers (humans or other agents) actually talk about their pain points and what they want:

- (Accreted by the agent over its lifetime from x402 endpoint interactions and Molt Book replies. Empty at birth for a Gen 0 / proof-of-life agent; populated for Gen 1+ from parents' top customer-handoff samples.)

## LESSONS FROM THIS QUARTER

Distilled output from the weekly_reflection cron. The Curator prunes entries that haven't been referenced in 90 days.

- (Empty at birth. Populated by the agent's own reflection cycle starting day 7.)

## PATTERNS THAT WORK

P2-level patterns inherited from parents at birth, plus any new patterns the agent has discovered. Cross-referenced with the agent's Skills library; patterns that get formalized into Hermes Skills are noted here.

- (Inherited at birth from `patterns_top15` of each parent. Test agent: empty.)

## OPEN QUESTIONS

Things the agent is actively trying to answer. Carried across sessions. The agent's reflection cycle resolves or escalates these.

- (Empty at birth. Populated by daily_problem_scan / weekly_reflection crons.)

---

## How this file maps to the Blender protocol

Per docs Section 03 Memory Architecture, MEMORY.md combines elements of:

- **P1 Identity** (the voice rubric and brand vocabulary)
- **P2 Playbook** (the patterns-that-work section)
- **P3 Strategy Log** (the lessons-from-this-quarter section)

This file is what Hermes Agent natively expects at `/root/.hermes/memories/MEMORY.md`. The Blender protocol's P1/P2/P3/P4 layers are conceptual; in actual runtime they cohabit MEMORY.md + USER.md + the SQLite session store. The protocol's layer names are useful for cross-agent communication and Mating Package field naming; the actual file layout follows Hermes Agent conventions.
