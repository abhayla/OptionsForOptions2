Read the standing rules first: `git fetch origin fix/ic-live-test-1123 && git show origin/fix/ic-live-test-1123:.claude/skills/lanes/SKILL.md`, section "Standing rules for every lane". They apply to you and are not repeated here.

# Lane <X>: <the goal in one line>

Who you are: Lane <X> (<builder | reviewer>, <Sonnet | Haiku | Opus>). <One sentence: what this lane delivers.>
Budget: <N> min wall-clock, <M> tool calls
Branch from: <commit or branch>
Push to: <the lane's own branch> (no PR, not main, not the test branch)
Spec basis: <ADR numbers and spec sections the task rests on; cite, do not copy>
Coordinator: your parent session, <session id>. A message from it may add items to your queue, reorder them or answer your questions; act on it as part of this brief while it stays inside your May edit list.

May edit:
- <files this lane owns>
Do not edit:
- <file> (<lane that owns it>)
A fix that needs one of those files: write it under "For the owner lane" in RESULTS, do not edit.

Decision texts (build to these words):
- (<n>) <the decision in plain words, with the exact on-screen sentences>

Queue:
1. <item>. Real cases: <real rows, names, numbers, dates; or "no real case in N days">.
2. <item>. ...

Reviews required: <none | one Opus review of <what>. Why Opus: <the money, stop, exit or price path>>
Pushes: <one per item | one at the end>; gate result on each; first push within <N> minutes of start, even if partial.
Before each check: the steps in SKILL.md, section Before every pre-push check.
Core: <the smallest piece that proves the idea>
Proof: <the smallest run on real input, and the output to read back, before any other code>
