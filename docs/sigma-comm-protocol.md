# ΣComm — Compressed Agent Communication Protocol

## Why
Agents communicate in full prose. 5 agents × back-and-forth messages = massive token overhead.
ΣMem proved LLMs can read/write compressed notation reliably. Apply the same to agent comms.

## Message Format

```
[STATUS] BODY |¬ ruled-out |→ actions |#count
```

### Status Codes
✓ = done/complete
◌ = in progress (partial result)
! = blocked (needs something)
? = need input/clarification
✗ = failed
↻ = retry/reattempt

### Body
Compressed content using ΣMem-style notation:
- |=separator, >=preference, →=leads-to, +=and, !=critical
- comma-separated items within sections
- pipe-separated sections

### Anti-messages (¬)
What was NOT found, NOT the issue, NOT done. Prevents receiving agent from assuming.

### Action Advertisements (→)
HATEOAS-style: what the sending agent can do next, based on current state.
Receiving agent/orchestrator uses these to decide next steps.

### Checksum (#)
Item count for verification. #3 means 3 items in the body.

## Inbox Infrastructure

Agents communicate via markdown inbox files at `~/.claude/teams/{team}/inboxes/{name}.md`.

### Inbox structure
```markdown
# inbox — {agent-name}

## processed
✓ ux-researcher(26.3.7): _state-feedback, agreed-on-logging |#1
✓ user(26.3.7): logging-sufficient-for-v0.1 |#1

## unread
## from:tech-architect ts:26.3.7
◌ registry-coupling: _last_state accessed 5x |→ need-your-take-on-DX-impact |#1

---
```

### Inbox processing
1. Read everything under `## unread`
2. Process each message
3. Compress processed messages into ΣComm summaries under `## processed`
4. Clear `## unread` section

### Writing to a peer's inbox
Append under their `## unread` section:
```
## from:{your-name} ts:{date}
{ΣComm message}

---
```

### Messages from user
User messages arrive in plain language. Respond via workspace open-questions or your findings section.

## Shared Workspace

Current task lives at `~/.claude/teams/{team}/shared/workspace.md`:

```markdown
# workspace — {task description}
## status: active

## task
{description of current task}

## findings
### {agent-name}
{agent writes findings here — ΣComm for efficiency}

## convergence
{agent-name}: ✓ {summary} |→ {next-available}

## open-questions
{plain language — things needing user input}
```

### Workspace rules
1. Write to YOUR section under findings — don't edit peers' sections
2. After reading peers' findings, write agreements to convergence
3. Write user-facing questions to open-questions in plain language
4. Declare your status in convergence when done (✓) or still working (◌)

## Codebook (for agent system prompts)

```
## ΣComm Protocol
Messages use compressed notation. Format: [STATUS] BODY |¬ not-found |→ can-do-next |#count
Status: ✓=done ◌=progress !=blocked ?=need-input ✗=failed ↻=retry
Body: |=sep >=pref →=next +=and !=critical ,=items
¬=explicitly NOT (prevents assumptions)
→=available actions (HATEOAS: what you can do based on current state)
#N=item count (checksum: verify you decoded correctly)
Parse incoming ΣComm messages by expanding notation. Send responses in ΣComm.
If ambiguous, ask sender to clarify rather than assuming.
```

## HATEOAS Integration

Each agent is a state machine:
- State determined by current task progress
- Available actions change with state
- Orchestrator navigates agents by following → advertisements

Agent states (generic):
- idle → waiting for assignment
- working → actively processing
- partial → have intermediate results
- done → completed, results ready
- blocked → need external input
- failed → encountered unrecoverable error

## Examples

**Review finding (agent-to-agent):**
```
✓ auth-review: jwt-expiry-no-validate(!), pwd-md5>bcrypt, no-rate-limit-login |¬ session-mgmt, cors |→ fix-jwt(small), fix-hash(needs-db-migration), add-rate-limit(small) |#3
```

**Blocked:**
```
! test-suite: 14/20 pass, 6 fail in auth-module |¬ api-tests, db-tests |→ need-auth-fix-first |? skip auth tests? |#6-fail
```

**Progress:**
```
◌ refactor-api: 3/7 endpoints migrated (users, orders, products) |→ next: payments, inventory, reports, admin |¬ no-breaking-changes-so-far |#3-done-4-remaining
```

**Convergence declaration:**
```
tech-architect: ✓ review-complete |resolved: 4/6, new: 3 |→ ready-for-synthesis
```
