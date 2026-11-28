---
paths:
  - "docs/process/**"
  - "tests/**"
  - "tests_app/**"
  - "frontend/tests/**"
  - ".claude/skills/lanes/**"
---
# Scope: path-scoped (test plans, process docs, tests, lanes skill)

# Cloud first: the PC only for what needs the PC

Owner, 2026-11-28, verbatim: "Walks the plan in a browser before your PC does - if this can be done then why using PC to do it?" and "PC is needed only for what the cloud cannot have - Update the required rules for this."

- **T1** Every check of a test plan is classed CLOUD or PC ONLY before a round, with the reason in one phrase.
- **T2** CLOUD = logic, wording, dialogs, counts, states, refusals, closed-market behaviour, anything a test or a cloud browser with seeded or scenario data can prove. It is proven in the cloud before the round and not repeated on the PC.
- **T3** PC ONLY = needs the real database change on the owner's data, his real rows, the real link speed to his database, his machine, a broker session, or the live feed.
- **T4** A PC round is the PC ONLY list plus a cross-check sample of at most ten cloud-proven checks. A cloud-proven check that fails in the sample is a fault of the cloud method; find its root cause the same day.
- **T5** Walk a test plan once in the cloud against the build before it goes to the PC. Correct plan faults (wrong control, wrong address, a table or record that does not exist) before the round.
- **T6** On the PC: one browser window, one helper at a time, tabs closed after each check, stop below 3 GB free, never run the full push check there.
- **T7** Record each item's proof level: cloud test, cloud browser, PC, live market. Nothing is called done above the level it has.

Real case, 28 Nov round 1: 75 checks ran on the PC, 16 of 33 fail or partial rows were plan faults, memory fell to 1.7 GB of 15.7.

Counter: PC checks that the cloud could have run.
