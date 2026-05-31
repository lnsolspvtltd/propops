# PropOps — Agent learnings log

Living notes from agent sessions on **this machine**. Update when a new environment failure is discovered.

## Session: 2026-05-31

### Failure: `&&` in PowerShell

```
cd "...\propops" && git status
→ The token '&&' is not a valid statement separator
```

**Fix**: Use `;` or separate commands:

```powershell
Set-Location "c:\Users\shiva\OneDrive\Desktop\propops"; git status
```

PowerShell 7+ supports `&&`; this environment uses **Windows PowerShell 5.x** — assume `&&` is **unsafe** unless verified.

### Failure: `gh` not found

```
gh : The term 'gh' is not recognized
```

**Fix**: Install GitHub CLI, call full path, or use GitHub REST API with `curl.exe`. Authenticated actions need `GITHUB_TOKEN` (was **missing** in session env).

### Failure: `curl` is an alias

```
Invoke-WebRequest : Missing an argument for parameter 'SessionVariable'
```

**Fix**: Always `curl.exe`, never bare `curl` in PowerShell.

### Failure: long `winget` probe

`winget list` ran ~47s and was interrupted.

**Fix**: Skip broad package scans; use direct path checks or ask user once.

### Failure: checkout from `origin/main` on Windows

```
error: invalid path 'relative/path/to/file.py\nACTION: create | modify'
```

**Fix**: Branch from **local `main`** (which already removed invalid paths), not raw `origin/main`. Push local main cleanup before others clone on Windows.

### Git state observed

- Branch: `main`, clean working tree
- `main` **2 commits ahead** of `origin/main` (unpushed local commits — removes invalid Windows paths)
- Remote issue branches include `anvil/issue-*`, `phase3/issue-*` (stale `phase3/issue-33-35` deletes files — do not use)
- Active work branch: `phase3/issue-35`

### Open issues (API snapshot)

| # | Title |
|---|--------|
| 35 | Persistent nav bar + approval badge count |
| 36 | Simulate incoming email — live demo trigger |
| 37 | Settings page — IMAP configuration + org management |

Canonical workflow: see `.cursor/rules/propops-agent-workflow.mdc`.
