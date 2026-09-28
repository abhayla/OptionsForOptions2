---
paths:
  - "releases/**"
  - ".github/workflows/**"
  - "deploy/**"
  - "scripts/deploy*"
  - "**/*deploy*"
---
# Scope: path (deploy work: `releases/`, CI workflows, deploy scripts)

# Deployment: one production deploy a day, staging in windows, production hosts are not test benches

version: "1.0.0" (generalized for the project kit)

Why: several production deploys in one day burned scheduled job runs and CI minutes; staging rebuilt on every merge
on the same box that served production; and ad-hoc test runs on a live host competed with real traffic.

## P. Production

- **P1 At most ONE production deploy per day**, in the project's documented low-traffic window. No "one more fix"
  the same day. The only exception is a named outage recorded in the release record.
- **P2 A deploy ships a COMPLETE, locally proven bundle:** every fix done, every suite green, the end-to-end proof
  run, the runbook written. Never partial. No known open issue rides along unless it is named and accepted in the
  pre-deploy brief.
- **P3 Always ask before a production deploy, with a full brief:** (a) what is done, with proof; (b) cost so far
  (deploys, review rounds, CI runs); (c) what is pending and what users will see live; (d) a DEPLOY or DEFER
  recommendation with reasons; (e) if DEFER, what to finish first; plus free disk and release count on the host.
  Nothing deploys without the owner's typed authorization.
- **P4 Rollback is written first**, in the release record (`releases/R-###.md`), before the deploy starts.
- **P5 Verify in the same window:** served version, process alive, smoke checks and proof lines, recorded in the
  release record.
- **P6 Batch the traffic:** related fixes go as one PR or a stacked set; merge to the release line only when
  deploy-ready; prefer local checks over "push and see".

## S. Staging

- **S1 A merge is not a deploy.** The main branch never auto-deploys on push.
- **S2 Staging deploys in windows**, a small fixed number per day, timed just before the jobs that generate proof; a
  window deploys the current main head only if it differs from what is served and the diff is not docs-only.
- **S3 One manual "deploy staging now"** for a waiting proof, with a small daily cap enforced by the dispatch script
  (not by memory) and each use logged with its reason.
- **S4 The window timer runs on a scheduler the project already trusts** on the host (OS cron or a system timer,
  installed idempotently by the deploy script), never only on a CI schedule trigger, which may silently not fire.
- **S5 Let a bundle soak on staging** for at least one full cycle of its scheduled jobs, and read the proof lines,
  before the production window.
- **S6 Make a deploy cheap:** a build cache or a CI-built artifact, so a window costs minutes, not a build on the
  serving host.

## H. Hosts

- **H1 No ad-hoc runs on a production or staging host.** A host is used for the deploy itself, the staging soak
  (deploy through the real pipeline and READ the logs), and reading state (logs, the app's own read paths, process
  status, disk). Test suites, scripts, probes and experiments need the owner's explicit OK for that one run.
- **H2 Correctness runs happen off the host,** in local worktrees with the same pinned packages; host-OS-specific
  behaviour is proven on a disposable CI runner, once per bundle.
- **H3 Disk and release retention:** the deploy script keeps a small fixed number of releases per environment (the
  current one never pruned) and refuses to deploy above 80% disk used; logs rotate; a weekly job prunes old releases,
  caches and temp files and reports disk use.
- **H4 A process-stop command never matches its own command line** (a pattern kill that appears in the caller's own
  arguments kills the caller); build the pattern at runtime or stop by process id.

## CRITICAL RULES

- MUST NOT deploy to production more than once a day, or without the owner's typed authorization after a full
  pre-deploy brief.
- MUST ship only complete, locally proven bundles, with the rollback written before the deploy.
- MUST verify the deploy in the same window and record it in the release record.
- MUST NOT auto-deploy staging on every merge; MUST deploy staging in capped windows on a trusted host scheduler.
- MUST NOT run tests, scripts or experiments on a production or staging host without the owner's OK for that run.
- MUST keep release retention and a disk ceiling in the deploy script.
