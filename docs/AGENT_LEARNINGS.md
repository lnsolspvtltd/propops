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
- Active work branch: `phase3/issue-36`
- **GitHub CLI 2.93.0** installed via `winget install GitHub.cli`
- Use `$env:GH_TOKEN` from `git credential fill` for `gh` when `gh auth login` fails (token lacks `read:org`)
- **PR #42** merged (issue #35) — **mistake: merged without FORGE approval**; do not repeat
- **PR #43** open (issue #36) — awaiting FORGE review before merge
- Repo had stray `---` lines and broken `config.py` / `pyproject.toml` — fixed incrementally

### Mandate: NEVER merge without FORGE approval

**Rule (no exceptions):** A PR may be merged only when:

1. FORGE / Claude code-review bot has left a GitHub review with **`APPROVED`**, or
2. An **external human user** explicitly instructs merge (e.g. “merge PR #43”).

**Not sufficient for merge:** green CI, agent self-confidence, “continue issue cycle”, or empty `reviews[]`.

**Past mistake — PR #42:** Issue #35 PR was merged before FORGE reviewed/approved. That violated the intended workflow. All future PRs (#43 onward) must wait for `reviewDecision: APPROVED` or explicit user merge command.

**Polling example:**

```powershell
& "C:\Program Files\GitHub CLI\gh.exe" pr view 43 --repo lnsolspvtltd/propops --json reviewDecision,reviews
```

If `CHANGES_REQUESTED`: fix on issue branch, push, reply to comments, re-invoke FORGE, re-poll. If no reviews yet: invoke FORGE — do **not** merge.

### Mandate: Pre-FORGE self-review gate (every cycle)

**Before every commit/push** during a FORGE review loop:

1. Read diff since last push
2. Self-review as FORGE (security, auth, org scoping, tests, prod guards, token storage)
3. Fix all fixable issues locally
4. Run tests
5. Commit + push only when self-review is clean
6. Then invoke FORGE

**Goal:** Fewer FORGE round-trips and lower API cost.

### Mandate: FORGE review batches (3 iterations each)

- **Batch 1:** iterations 1–3 — PR #43 completed with CHANGES_REQUESTED each time; escalation posted
- **Batch 2:** iterations 4–6 — authorized by founder for PR #43
- After each batch of 3 without APPROVED: STOP, post PR comment, ask external user
- Next batch (7–9, …) requires explicit external authorization

Track within batch: e.g. `4/6`, `5/6`, `6/6`.

### Mandate: 3-iteration FORGE review cap (per batch)

After each PR open/update (within an authorized batch):

1. **Self-review** diff as FORGE → fix → commit + push
2. **Invoke FORGE** via Helix `review_pr()` (see `.cursor/rules/propops-agent-workflow.mdc`)
3. **Wait** for FORGE review comment on the PR
4. **Implement all feedback**, self-review again, push to same issue branch
5. **Repeat** — max **3** complete cycles per batch (track e.g. 4/6, 5/6, 6/6)
6. After **3 iterations in batch** without FORGE approval: **STOP**, post escalation comment on PR, ask **external user** — do **not** merge

**Do NOT use** `run_review_loop` for PropOps — it auto-fixes via ANVIL and may auto-merge.

**Invocation (documented for PR #43):**

```powershell
Set-Location "c:\Users\shiva\OneDrive\Desktop\LN SOLS MULTI AGENT\ln-sols-multi-agent"
python -c "from agents.forge.tools.code_reviewer import review_pr; r = review_pr('https://github.com/lnsolspvtltd/propops/pull/43'); print(r.review.overall_rating, r.review.approved, len(r.review.issues))"
```

### Open issues (API snapshot)

| # | Title |
|---|--------|
| 35 | Persistent nav bar + approval badge count |
| 36 | Simulate incoming email — live demo trigger |
| 37 | Settings page — IMAP configuration + org management |

Canonical workflow: see `.cursor/rules/propops-agent-workflow.mdc`.
