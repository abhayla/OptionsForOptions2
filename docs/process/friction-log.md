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
| 2026-11-27 | coordinator | The pre-push check takes 35 to 45 minutes per push; decision-record pushes ran 6 times; a stopped run restarts from zero. | 6 pushes, 2 restarts | 35 to 45 min per run | wait | new |
| 2026-11-27 | lanes | Fresh lane sessions each lost one check run because `ruff` was not installed; 3 lanes built PostgreSQL by hand. | 4 lanes, 3 lanes | 4 failed runs, 3 hand builds | missing tool | new |
| 2026-11-27 | coordinator | Every lane brief repeated about 500 words of the same rules. | 18 briefs | about 9,000 words | repeat by hand | new |
| 2026-11-27 | coordinator | Most lanes cannot message the coordinator ("untrusted device"); status was read from a line at the top of a results file, polled hourly. | hourly | 1 poll per lane per hour | missing feature | new |
| 2026-11-27 | coordinator | Each owner answer needed four manual steps: record the row, tell the lane, commit, queue a push. | 17 answers | 68 manual steps | repeat by hand | new |
| 2026-11-27 | coordinator | The status page was updated by hand-written update commands before a tool was built at 18:00. | about 25 times | about 25 hand edits | missing tool | done |
| 2026-11-27 | coordinator | Scheduled wake-ups of the coordinator did not visibly fire. | several times | missed check-ins | missing feature | new |
| 2026-11-27 | coordinator | The coordinator misstated the clock time by 5 to 30 minutes. | at least 6 times | 5 to 30 min of error each | same mistake twice | new |
| 2026-11-27 | coordinator | A question was put to the owner although an existing rule answered it (second occurrence; finding owner-question-asked-without-the-requirement-that-answered-it). | 2 times | owner time | same mistake twice | new |
| 2026-11-27 | coordinator | A faster pre-push check, proven on 26 Nov, sat unadopted because its last fix was never reviewed. | 20 hours | 20 h of slow runs | wait | new |
| 2026-11-27 | coordinator | The plan gave first-version times 3 to 6 hours too slow and a second version with 4 untestable steps; an independent review found 20 findings. | 2 versions, 20 findings | review rounds | unclear rule | new |
| 2026-11-27 | lane | A lane instruction ("fail closed when no freeze quantity is stored") would have refused every SENSEX order; the lane caught it. | 1 time | near miss | unclear rule | new |
| 2026-11-27 | PC session | The PC session posted the server address in a public PR comment. | 1 time | exposure of an address | same mistake twice | new |
| 2026-11-27 | coordinator | Two lanes were asked to edit a file another lane owned (one-line changes); the rule "one file, one lane" had no exception path. | 2 lanes | 2 blocked lanes | unclear rule | new |
| 2026-11-27 | owner | Screen tests of stops, exits and speed can run only on the owner's PC in market hours. | every test day | owner time | owner time | new |
| 2026-11-27 | coordinator | Two lanes sat blocked waiting for the coordinator (one asked which part to do next, one ran out of its budget); found only by reading the session list, after about 60 minutes | 2 lanes, about 60 min | about 2 lane-hours | wait | new |
| 2026-11-27 | coordinator | Four lanes reported installing ruff and three building PostgreSQL although both are already installed in every cloud session (ruff at /root/.local/bin, PostgreSQL 16 not started) | 7 lanes | 4 failed check runs of about 40 min | missing tool (false) | new |
| 2026-11-27 | coordinator | The coordinator put work off to 'Saturday in the daytime' (issue filing, owner questions) although nothing but the live market needed waiting; the owner had to say so | 3 items | about 2 hours of idle coordinator time | owner time | new |
| 2026-11-27 | coordinator | Three server lanes built half a fix and handed the screen half to a lane that did not exist yet | 3 hand-overs | one extra lane and about 2 hours | unclear rule | new |
| 2026-11-27 | coordinator | A lane ended its turn waiting on a long background run and stayed idle after the run finished | 3 times (G2 60 min, R2 60 min, Z 60 min) | about 3 lane-hours | wait | new |
| 2026-11-27 | coordinator | Issues were filed an hour before their stage rows were pushed, so GitHub's coverage check went red on one commit | 1 commit, 1 hour gap | 1 red check run | same mistake | new |
| 2026-11-27 | coordinator | The build lane could merge only clean branches while the lanes that owned the conflicting files had closed; 6 of 11 fix branches sat out of the build for 3 hours | 6 of 11 branches | 3 hours | unclear rule | new |
| 2026-11-27 | coordinator | The coordinator told the owner twice that the build lane had pushed nothing; its scan read a stale branch list | 2 times | 2 wrong reports to the owner | same mistake | new |
