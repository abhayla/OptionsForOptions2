# Owner questions and notes, GC-ICSAFE (opened 2026-11-10 evening for the 11 Nov run)

Plain words first. Each entry says what is asked, what I recommend and why. Nothing here blocks the run.

## Q1. Please approve the demo-ready checklist (standing direction step 2)

**What it is:** `docs/process/demo-ready-checklist.md`, a draft list of everything Zerodha must see before we reapply
for multi-user access. Part A is Zerodha's own ten written asks (ticket 403947, finding F-31). Part B is the nine
things that must work on screen first (ADR-060 and the goal sentence of the standing direction).

**What I am asking:** is this the right finish line? Three choices:

1. **Approve as written (my recommendation).** Why: every row is either Zerodha's own words or a step of the journey
   you already approved on 10 Nov; nothing was added from my side. Each state is a measurement or says `unmeasured`.
2. Approve with changes: tell me the rows to add, drop or reword.
3. Not yet: tell me what is missing.

**What you will notice when reading it:** most of Part A is "not written" or `unmeasured`. That is honest, not a
fault of the list: the answers to Zerodha can only be written after a second person can log in on a hosted link and
one real order has gone through (rows B1 and B5). Those two are standing direction step 4 and still need your
decisions on host, spend and lifting the paper-only rule (ADR-281).

**One correction to the plan:** the contract said F-31 has nine asks. Counted from the ticket text there are ten
(the API list and the "is use limited to these five" question are separate asks). All ten are in the list.

Spec basis: finding F-31 (`spec/findings.md`), ADR-060, `docs/process/standing-direction.md` step 2 ("The owner has
approved the list").
