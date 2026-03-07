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

## Examples

### Current (prose):
```
I've finished reviewing the authentication module. I found three issues:
1. JWT token expiration is not being validated on refresh
2. Password hashing uses MD5 instead of bcrypt
3. No rate limiting on the login endpoint
I didn't find any issues with the session management or CORS configuration.
I recommend fixing the JWT issue first since it's the most critical security risk.
The MD5 migration will need a database migration to rehash existing passwords.
```

### ΣComm:
```
✓ auth-review: jwt-expiry-no-validate(!), pwd-md5>bcrypt, no-rate-limit-login |¬ session-mgmt, cors |→ fix-jwt(small), fix-hash(needs-db-migration), add-rate-limit(small) |#3
```

### More examples:

**Blocked agent:**
```
! test-suite: 14/20 pass, 6 fail all in auth-module |¬ api-tests, db-tests |→ need-auth-fix-first |? should I skip auth tests and continue? |#6-fail
```

**Progress update:**
```
◌ refactor-api: 3/7 endpoints migrated (users, orders, products) |→ next: payments, inventory, reports, admin |¬ no-breaking-changes-so-far |#3-done-4-remaining
```

**Handoff:**
```
✓ schema-design: users(id,email,role,hash,created), sessions(id,user_id,token,expires) |→ ready-for: migration-agent, test-agent |¬ no-admin-table(deferred per decision) |#2-tables
```

**Failed task:**
```
✗ deploy: build-ok but container-crash-on-start |cause: missing-env-var(DATABASE_URL) |¬ not-code-issue, not-docker-config |→ need: env-config-from-infra-agent |#1-blocker
```

## Codebook (for agent system prompts)

This block gets prepended to each agent's system prompt:

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

The orchestrator sees → actions from all agents and routes work accordingly,
just like sigma-mem navigates memory files based on → links.

## Token Savings Estimate

Typical prose message: ~80-120 tokens
ΣComm equivalent: ~20-35 tokens
Compression: ~3-4x per message

5 agents × 10 messages each × 4x compression = 200 messages worth of budget in 50 messages of tokens.
Or: same budget, 4x more communication, better coordinated agents.
