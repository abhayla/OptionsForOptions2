# Handover

Updated 2026-09-28 by the Startup-Factory session that created this project (Factory decision OD-29).

## DONE
- Project created from Factory kit 1.2.0 with the production seatbelt; private repo `abhayla/OptionsForOptions2`;
  `python tools/kit_selftest.py .` all checks passed; CI green on the first push.

## PENDING (from the owner)
- The project idea: what this options project should do, for whom, and what "done" looks like. Nothing has been
  decided yet; there are no ADRs.

## NEXT
1. Run the `intake` skill with the owner's idea: one question per turn, each answer written as the next
   `spec/decisions/ADR-###.md` the same turn, then fill this file and CLAUDE.md, then name the core proof.

## Open decisions
- Everything about the product (intake has not started).

## Legacy code (reference only)
- `abhayla/OptionsForOptions` (private, created 2021, last pushed July 2025) is an older ASP.NET WebForms + MySQL
  options app with a `Strategy` folder. The owner chose (2026-09-28) to leave it exactly as it is and start this
  new repo. Read it for ideas (strategies, formulas) only with read-only commands; never push to, rename or change
  it. Anything reused is rewritten here under the spec, with a note naming the legacy file it came from.
- `D:\Abhay\Ventures\OptionsForOptions` locally holds only a `.remember/` folder, no code; leave it alone.
