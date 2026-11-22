# CLAUDE.md

## Environment

This is a Windows/PowerShell environment - PS1 status line config, bash assumptions, and Unix tools (jq) often don't apply. Prefer PowerShell or Node-based solutions and verify stdin parsing works in Git Bash.

## Verification

After implementing status line / hook / config changes, explicitly verify the result persists across a restart rather than assuming success.

## Tooling

Before reviewing code, check if `gh` CLI and required tooling (npm, jq) are installed; if missing, state the fallback approach upfront instead of failing mid-task.

## Debugging

When fixing a bug, verify the root cause before applying a fix - state the diagnosis and confirm it matches symptoms (e.g., check exit codes, race conditions in effects) rather than guessing.

## Model choice for subagents

When spawning an Agent without a definition that sets `model:`, pass `model` yourself — cheapest model that still does the job well:

- `haiku` — pure lookup: find files, grep, list/inventory, summarise one file, fetch a page.
- `sonnet` — default for scoped work: implement from a clear spec, run tests, collect a BOM, slicer settings, write docs.
- `opus` — only where a miss costs real money or time: pre-print CAD review, geometry/fit reasoning, architecture, security review, ambiguous debugging.

When unsure between two, pick the stronger one for reviews/verdicts and the cheaper one for gathering.
Skill/agent frontmatter `model:` wins over this table.

## Session handover

When a self-contained task is finished and the next one is a different task (or old reasoning in this session is going stale), don't just carry on:
1. Save anything only this conversation knows (pending requests, decisions, gotchas) to memory or the project README.
2. Offer a new session in one line, plus a `spawn_task` chip with a self-contained start prompt. The user clicks or ignores it.

Never do this mid-task, and never only because the session is long (compaction handles that).
