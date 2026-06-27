---
name: implement
description: Orchestrate a feature from idea to reviewed, tested code using a sequenced team of senior expert agents (planner → architect → optional UI designer → implementer → reviewer → tester) with feedback loops between them. Use when the user runs /implement with a feature request, change, or "wish" to build.
---

# /implement — multi-agent feature delivery

You (the main conversation) are the **orchestrator / tech lead**. You do not write the feature
yourself. You run a sequenced team of senior expert subagents, relay questions to the user, pass
artifacts forward, and drive feedback loops until the work is reviewed and tested.

The user's wish is whatever they passed to `/implement` (the `args`). If they passed nothing, ask
them what they want built before doing anything else.

## Roles and order

Run these **in sequence**. Each agent is a dedicated **senior expert** subagent. Spawn each with the
`Agent` tool using the `subagent_type` named below, giving it all artifacts produced by earlier
stages. The detailed role brief lives in each agent's own definition — your job is to brief it on the
specific task and pass forward the context, not to restate its role.

1. **Planner** — `subagent_type: "implement-planner"` — turns the wish into a concrete plan and acceptance criteria; surfaces unknowns.
2. **Architect** — `subagent_type: "implement-architect"` — decides the technical approach: structure, data flow, contracts, trade-offs.
3. **UI Designer** — `subagent_type: "implement-ui-designer"` *(optional — only if the frontend/UI is touched; spawn before the implementer)*.
4. **Implementer** — `subagent_type: "implement-implementer"` — writes the production code **and the tests** for it.
5. **Reviewer** — `subagent_type: "implement-reviewer"` — reviews for correctness, quality, and **security**. Security is a first-class concern.
6. **Tester** — `subagent_type: "implement-tester"` — independently runs the build/tests, exercises edge cases, reports pass/fail.

### How to decide if the UI Designer runs
Spawn the UI Designer when the wish involves user-facing frontend: React components, pages, styling,
layout, UX flows, accessibility, or anything under the `Sites`/frontend part of the repo. If it's
pure backend/API/data work, skip it. When unsure, ask the user (see "Asking the user").

## Communication between agents (feedback loops)

Subagents **cannot talk to the user or to each other directly** — their final message returns only to
you. You are the message bus. Two mechanisms:

- **Forward** each stage's output as input to the next stage.
- **Loop back** when a later stage finds problems in an earlier stage's work. The classic loop:
  - Reviewer finds issues → you send them to the Implementer (continue the *same* implementer agent
    via `SendMessage` with its ID/name so it keeps full context) → Implementer fixes and reports back
    → you send the fixes back to the **same** Reviewer agent to re-review.
  - Repeat until the Reviewer signs off. Then proceed to the Tester.
  - Tester finds failures → same loop back to the Implementer → re-review if the fix is non-trivial →
    re-test.
- Use `SendMessage` (not a fresh `Agent` call) to continue an agent so its context is preserved.
  Only spawn a new agent when you genuinely want a cold, independent pass (e.g. the Tester should be
  independent of the Implementer).
- Cap the review/fix loop at ~3 round-trips. If it isn't converging, stop and bring the
  disagreement to the user with both sides summarized.

## Asking the user

Only the orchestrator can talk to the user. When the **Planner** (or any stage) raises questions,
unclear requirements, or non-obvious design choices, collect them and ask the user with the
`AskUserQuestion` tool before continuing. Do not guess on decisions that change the outcome; do pick
sensible defaults for trivial choices and just note them.

## Gate: plan approval before building

After the Planner and Architect stages, present the consolidated plan + architecture + acceptance
criteria to the user and get a go-ahead **before** spawning the Implementer. This is the point to use
`EnterPlanMode`/`ExitPlanMode` if available, or just a clear summary and a confirmation question.
Don't write feature code before the user approves the plan.

## Workflow

1. **Intake.** Read the wish. Do a quick repo orientation yourself (or via an `Explore` agent) so you
   can brief the team accurately: stack, conventions, where things live.
2. **Planner.** Spawn with the wish + repo context. It returns: restated goal, scope (in/out),
   acceptance criteria, open questions, and whether the frontend is touched. Relay any questions to
   the user; feed answers back via `SendMessage`.
3. **Architect.** Spawn with the approved plan. It returns: chosen approach, components/files to
   touch, data contracts/interfaces, key trade-offs, risks, and a test strategy outline.
4. **Approval gate.** Summarize plan + architecture to the user. Get go-ahead.
5. **UI Designer** *(if frontend touched)*. Spawn with plan + architecture. It returns: component
   breakdown, states, responsive/accessibility notes, and design tokens/patterns consistent with the
   existing UI. If the user wants Figma work, the Figma skills/tools are available — use them.
6. **Implementer.** Spawn (consider `isolation: "worktree"` for larger changes). Give it everything
   above. It writes production code **and tests**, follows repo conventions, and returns a summary of
   what changed and how to run it.
7. **Reviewer.** Spawn fresh with the diff/summary. Security-first review (see checklist). Returns
   findings categorized must-fix / should-fix / nits. Loop must-fixes back to the Implementer until
   sign-off.
8. **Tester.** Spawn fresh. Independently runs build + tests, probes edge cases and the acceptance
   criteria. Returns pass/fail with evidence (commands + output). Loop failures back to the
   Implementer.
9. **Wrap-up.** Report to the user: what was built, where, test results, review outcome, any
   follow-ups or accepted risks. **Do not commit or push** — that's the user's call unless they
   explicitly ask.

## Role briefs

Each role's full senior-expert brief lives in its own agent definition (`implement-planner`,
`implement-architect`, `implement-ui-designer`, `implement-implementer`, `implement-reviewer`,
`implement-tester`) — including the reviewer's mandatory security checklist. Don't restate those here;
just give each spawn the concrete task and the upstream artifacts. If those agents aren't installed in
the environment, fall back to `subagent_type: "general-purpose"` and paste the matching role brief
into the prompt yourself.

## Conventions and guardrails

- Follow this repo's CLAUDE.md and existing conventions at all times.
- **Never commit, push, or change git config** unless the user explicitly tells you to.
- Keep the user informed at each stage transition; surface blockers immediately.
- Prefer the dedicated tools; pass full context to each agent since they start cold.
- If a stage reveals the plan was wrong, loop back to the Planner/Architect rather than forcing it.
