# Scope: global (this project)

# Evidence and proof: prove the core first, prove every claim, answer honestly

version: "2.0.0" (lean: OD-117)

- **E1 Ask what, not how.** Below 95% confidence about WHAT is asked, ask with the question tool, one question per
  call, recommended option first, Spec basis inside. Never ask what the spec, repo or a command can answer.
  Counter: owner questions asked vs questions the spec answered.
- **E2 Honest answers.** Name bad as bad with its cost; plain words, one concrete example per important claim.
  Counter: claims later found false.
- **E3 Core first.** New work opens with `Core:` / `Proof:`; step 1 is the smallest run on REAL input, output read
  back. A failing core stops the build. Counter: items whose core proof is recorded before other code.
- **E4 Evidence before claims.** A done/pass/merged claim ends with a table `| Claim | Evidence (command run this
  turn + result line) |`. Another agent's report is a claim: re-read the artifact first. Counter: claims without a
  command row.
- **E5 Defect fix = fix the class.** Carry RCA (one sentence), Class (data filter, size before and after), failing
  test first, class-level fix, ONE real-data proof, and a detection change or `No detection change: <reason>`.
  Counter: defects of the same class recurring.
