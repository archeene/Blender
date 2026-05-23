# Plan docs

When to write one, what goes in one, and why.

## When

Write a plan doc here BEFORE implementing anything that:

- Touches more than 3 files
- Adds a new MCP server or skill
- Changes a load-bearing data shape (registry schema, mating JSON, cron_jobs.json)
- Would take a fresh engineer more than a few hours to do safely
- Could be done multiple plausible ways and you want to lock in one

Do NOT write one for:

- Single-line bugfixes, typo corrections, documentation tweaks
- Pure version bumps or grace_period adjustments
- Things you could review the diff for in under 60 seconds

If you're unsure, write one. Plan docs are cheap compared to ripping out a misimplementation.

## Format

Each plan lives at `docs/plans/YYYY-MM-DD-<topic>.md` and contains, in order:

1. **Goal** in one sentence. What does "done" mean for the user.
2. **Why** in one paragraph. What stops working today without this. What's the cost of not doing it.
3. **Interface specification.** Every file that gets created or modified, with the exact function signatures, MCP tool shapes, env var names, or markdown section headers. The reader should be able to picture the diff before any code is written.
4. **Verification strategy.** The exact commands or checks that prove the work is done. Specific test names, specific files to grep, specific URLs to HTTP GET. No "verify the tests pass" without naming the test file.
5. **Proof of done.** What output looks like when the verification commands run cleanly. Paste the expected output shape if you can.
6. **Out of scope.** A bulleted list of things this plan deliberately does not address, so reviewers don't ask about them.

## Workflow

1. Draft the plan. Iterate until it would be unambiguous to a fresh engineer.
2. Share with the operator. Review is cheap at this stage; revision is cheap.
3. Implement against the plan, no improvisation. If the implementation has to diverge, edit the plan first to record the deviation and why, then code.
4. Before opening a PR, spawn a read-only review subagent that takes the plan doc + the diff and returns gaps or over-engineering.
5. PR opens with a link to the plan doc.
6. After merge, the plan doc stays as the historical record. Don't delete it.

## Why this exists

Past sessions shipped PRs that were either too small (single-file changes that needed batching) or too large without a clear interface contract (everything got built before anyone knew what "done" looked like). Plan docs are the fix for both: they force batching at the planning stage and they pin the interface contract before code happens.

This convention was adopted after observing the cost of NOT having it. See `docs/process/lessons.md` for the specific patterns the article-from-the-thread diagnosed.
