---
name: improve
description: Turn the friction log into ranked recommendations for the owner. Use at the end of a session or a test day, when the same problem has happened twice, when a wait or a manual repeat passes the thresholds below, or when the owner asks "what can be improved". Invoke as /improve.
---

# Improve (recommend fixes without being asked)

The owner's instruction of 27 Nov 2026: find the fix for every problem, recommend it unasked, and let the owner decide.
This skill extends `.claude/rules/kit/learning.md` (L1 to L3 record and fix defects; this one also covers waits,
manual work and missing features). The rule is `.claude/rules/project/improve-proactively.md`.

## What creates a row in `docs/process/friction-log.md` (append only, same turn)
- The same failure or mistake a SECOND time.
- Any wait over 10 minutes that repeats.
- Any manual step done a THIRD time.
- Any workaround.
- Any time the owner had to ask for something the session could have proposed.

## Steps
1. **Read** the rows with status `new`. Group them by cause, not by symptom. Add a number to each group (count, minutes).
2. **Pick the remedy kind**, first one that works: remove the step; a script; a hook or check that runs by itself; a
   skill; a sub-agent definition with the right model; a setting of the cloud environment (set-up script, network); a
   scheduled task; a rule in words only as the last resort. A rule people must remember is the weakest fix.
3. **Check the current Claude Code documentation before recommending a feature.** Dispatch the `claude-code-guide`
   agent with one narrow question ("can a hook do X?"). Never recommend a feature from memory. Give the
   documentation link in the recommendation.
4. **Write each recommendation in this shape:**
   - Problem (with the number from the log)
   - Recommendation
   - What it changes for the owner
   - Cost to build: small / medium / large
   - Risk
   - What happens if we do nothing
   - Who decides: the owner (money, access, a product behaviour, a change outside the repo) or the session (its own
     technical call)
5. **Present to the owner,** ranked by time or money saved, at most 7 at once, bad news first, plain English.
   Technical calls the session may just do go in a list headed "doing this unless you object". Owner calls are asked
   one at a time with the question tool, recommended option first.
6. **Record the outcome** in the log's status column (`recommended`, `decided: do`, `decided: not now`, `done`). For a
   `decided: do`, write a work item or a lane brief the same turn.
7. **A declined recommendation is not raised again** unless its log numbers have doubled since the owner declined.

Spec basis for any question to the owner still applies (`spec-first.md` R2).
