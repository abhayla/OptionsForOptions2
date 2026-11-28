# Harvest issue draft: improve proactively (org-wide), 27 Nov 2026

Not filed. The coordinator files it in abhayla/Startup-Factory with the label `harvest`.

## Title
harvest: log friction and recommend improvements without being asked (owner rule, all projects)

## Why
Owner, 27 Nov 2026: "Whatever problem you are facing, you should find out the fix for it and provide recommendations.
This should be an org-wide rule, for all my projects. If we are doing the same mistake, or Claude Code thinks some good
feature from Anthropic can improve the work of the project it is used in, it should proactively recommend to the
owner and let the owner decide."

Source project: OptionsForOptions2. On 27 Nov the coordinating session hit the same frictions many times (16 are in
its `docs/process/friction-log.md`: a reminder that fired about 60 times, a 35 to 45 minute check run 6 times, 17
owner answers each needing 4 manual steps) and proposed fixes only when the owner asked. The kit rule `learning.md`
covers defects (L1 to L3) but not waits, manual repeats or missing features, and it does not tell the session to
speak up unasked.

## Proposed kit files
Same text as the source project, by path in OptionsForOptions2 at the commit that adds them, inlined below.
1. `docs/process/friction-log.md` (template: header and columns, no seed rows)
2. `.claude/skills/improve/SKILL.md`
3. `.claude/rules/kit/improve-proactively.md` (always-loaded, 727 bytes; fits the 8192 cap in a template with the
   current three always-loaded kit rules, 6037 bytes)

## How a project adopts it
1. Upgrade the kit (copier) so the three files arrive; the rule and skill are kit-owned, the log is project-owned.
2. Run `python tools/kit_settings.py .` (no wiring change is needed; skills and rules load by path) and the kit
   self-test budget check.
3. Add a line under "Read first" in CLAUDE.md pointing to the log.
4. Optional later hardening: a Stop hook that counts `new` rows older than one session (the rule's Counter).

## Files

### 1. `.claude/rules/kit/improve-proactively.md`
~~~markdown
# Scope: global (this project)

# Improve proactively (owner, 27 Nov 2026; extends kit `learning.md` L1 to L3)

Owner: "Find the fix for every problem you face and recommend it, without waiting to be asked; the owner decides."

- **I1 Log.** When a threshold is met (same failure twice, a repeating wait over 10 min, a manual step a third time, any
  workaround, anything the owner had to ask for), add a row to `docs/process/friction-log.md` the same turn.
- **I2 Recommend unasked,** at session end and at the second occurrence: run the `improve` skill.
- **I3 Owner decides** money, product behaviour and anything outside the repo; the rest is your call, stated openly.

Counter: log rows still `new` after a session ended.
~~~

### 2. `.claude/skills/improve/SKILL.md`
~~~markdown
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
~~~

### 3. `docs/process/friction-log.md` (template)
~~~markdown
# Friction log

Append only. Every session and lane adds a row when a threshold in `.claude/skills/improve/SKILL.md` is met; nobody
deletes or rewrites a row except to change its status. The `improve` skill reads the rows with status `new`.
Rule: `.claude/rules/project/improve-proactively.md`.

Columns: date (IST); who (session or lane); what happened (one plain line); how often or how long (a number); cost
(minutes, tokens or failed runs); class (wait / repeat by hand / same mistake twice / missing tool / missing feature /
unclear rule / owner time); status (new / recommended / decided: do / decided: not now / done).

| Date | Who | What happened | How often / long | Cost | Class | Status |
|---|---|---|---|---|---|---|
| 2026-11-27 | coordinator | The cloud service's "unpushed commits" reminder fired while a push was already in its check. The reminder script is the cloud harness's own and cannot be edited. | 60 times | 60 turns | repeat by hand | new |
| Date | Who | What happened | How often / long | Cost | Class | Status |
|---|---|---|---|---|---|---|
~~~

## For projects without the kit: personal preferences text
Paste into Claude personal preferences (owner's rule of 27 Nov 2026):
~~~text
In every project, keep a friction log (docs/process/friction-log.md, or create it): add a row when the same failure
happens a second time, a wait over 10 minutes repeats, a manual step is done a third time, or you use a workaround.
Without being asked, at the end of a session and at any second occurrence, recommend fixes: prefer removing the step,
then a script, a hook or check, a skill, a sub-agent, an environment setting, a scheduled task; a written rule last.
Check the current Claude Code documentation before recommending a feature; never from memory. Give each
recommendation as: problem with number, recommendation, what it changes for me, cost, risk, what if we do nothing.
I decide anything that costs money, changes product behaviour or reaches outside the repo.
~~~
