# CLAUDE.md

## Environment

This is a Windows/PowerShell environment - PS1 status line config, bash assumptions, and Unix tools (jq) often don't apply. Prefer PowerShell or Node-based solutions and verify stdin parsing works in Git Bash.

## Verification

After implementing status line / hook / config changes, explicitly verify the result persists across a restart rather than assuming success.

## Tooling

Before reviewing code, check if `gh` CLI and required tooling (npm, jq) are installed; if missing, state the fallback approach upfront instead of failing mid-task.

## Debugging

When fixing a bug, verify the root cause before applying a fix - state the diagnosis and confirm it matches symptoms (e.g., check exit codes, race conditions in effects) rather than guessing.
