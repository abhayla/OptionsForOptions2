# Session handover 2026-10-15: moving work from the Windows VPS to another PC

Read `docs/process/session-handover-2026-10-12.md` first; this note only adds what changed since and what the
other PC needs.

## State

- **Everything is committed and pushed.** `main` = 281a8e6 (#202). Open branches on origin:
  `build/W-065-live-push` (8c175c2, main merged in, green locally, no PR yet) and `build/W-066-on-main`
  (4b78d8e, PARKED #172). No uncommitted work on the VPS.
- **W-065 live proof did NOT run.** The owner's Kite login never happened in the market window on 2026-10-12, so
  the proof is now overdue (run-discipline B1: a 2-working-day-overdue real-world proof is parked unless it runs
  next market day). The login app on the VPS was stopped on 2026-10-15.
- Nothing else changed since the 2026-10-12 handover.

## NEXT (on the other PC)

1. Set up the PC per `docs/process/session-handover-2026-10-07.md` (project `.env`, `GLOBAL.env`, SSH tunnel to
   the VPS PostgreSQL for `ofo_test`). First sync `GLOBAL.env` (below).
2. W-065 live proof, market hours (09:15-15:30 IST), worktree on `build/W-065-live-push`:
   - start the API with the project `.env` loaded, `DATABASE_URL` set to the `TEST_DATABASE_URL` value,
     `APP_ENV=development`, `LIVE_MARKET` unset, `PYTHONPATH=backend`:
     `python -m uvicorn ofo_app.main:create_app --factory --host 127.0.0.1 --port 8765`
     (the Kite redirect URL is `http://127.0.0.1:8765/kite/callback`, so the browser must run on the same PC);
   - owner logs in at `http://127.0.0.1:8765/broker/zerodha/login` (account per `KITE_EXPECTED_USER_ID`);
   - `python scripts/orchestrator/db_run.py <wt> python docs/research/kite-proof-2026-10-07/w065_live_push_proof.py --seconds 60`
     (exit 0 = at least 30 pushes, gap at least 1 s, LTP and P&L changed, health available; exit 2 = no Kite session);
   - stop the API; Opus verifier for W-065 AC-4; record evidence; PR; `merge_when_green.py`.
3. Then W-066 (#172), #200 (bounded round with an explicit end condition), #199.

## GLOBAL.env sync (VPS and personal PC)

The VPS cannot reach the personal PC, so the sync runs FROM the PC. Since the last verified sync (2026-09-12, 66
keys) the VPS gained 9 keys (74 now); the PC may have its own new keys, so the merge is two-way. The script sits on
the VPS at `C:\Abhay\scratch\global_env_sync.py`: it compares key names and value hashes (never prints a value),
backs up both files, copies keys missing on either side, keeps `NOTIFIER_URL` per machine (GLOBAL.md sync rule),
and leaves keys whose values differ untouched unless `--prefer local|remote` is given. On the PC:

```
scp -i ~/.ssh/ipodhan_vps Administrator@103.118.16.189:C:/Abhay/scratch/global_env_sync.py .
python global_env_sync.py --local D:/Abhay/GLOBAL.env --remote Administrator@103.118.16.189:C:/Abhay/GLOBAL.env --ssh-key ~/.ssh/ipodhan_vps
python global_env_sync.py ... --apply            # add --prefer remote|local only after reading the differing keys
```

The Hostinger copy (`/root/Abhay/GLOBAL.env`) is the third machine; run the same script against it from the PC.
