# claude-config

Personal [Claude Code](https://claude.ai/code) configuration — hooks, status line, agents, and skills for the `/implement` workflow.

## What's included

| File / Dir | Purpose |
|---|---|
| `CLAUDE.md` | Global instructions injected into every Claude Code session |
| `settings-template.json` | Hook and status line config (paths filled in by `setup.ps1`) |
| `notify.ps1` | Windows toast notifications on task completion / waiting for input |
| `focus-terminal.ps1` | Brings the terminal to the foreground when a toast is clicked |
| `statusline-command.sh` | Status line showing branch, model, and token usage |
| `agents/` | Implement workflow sub-agents (planner, architect, UI designer, implementer, reviewer, tester) |
| `skills/implement/` | `/implement` skill that orchestrates the agent pipeline |

## Prerequisites

- Windows 11 with [Claude Code](https://claude.ai/code) installed
- [Git for Windows](https://git-scm.com/) at `C:\Program Files\Git` (default)
- PowerShell 7+

## Setup

```powershell
git clone https://github.com/AlbinOdelstav/claude-config.git
cd claude-config
.\setup.ps1
```

If Git Bash is installed somewhere else:

```powershell
.\setup.ps1 -GitBashPath "D:/Git/bin/bash.exe"
```

The script copies all files into `~/.claude`, generates `settings.json` with the correct paths for your machine, and backs up any existing `settings.json` first.

Restart Claude Code after running the script.

## Updating

Pull and re-run `setup.ps1`:

```powershell
git pull
.\setup.ps1
```
