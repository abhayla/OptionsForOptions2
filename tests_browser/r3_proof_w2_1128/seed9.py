# Lane W2 set-up for I-48 / I-08: 5 more running paper trades (SQL fills, the market is closed) + an accepted plan on every running trade -> 9 planned rows in ofo_tg
import os, subprocess, sys, json, httpx
sys.path.insert(0, '/home/user/OptionsForOptions2/tests_browser/r2_plan_walk_1128')
os.environ.setdefault('TC_API_BASE', 'http://127.0.0.1:8010')
import seed_strategies as s
PSQL = s.PSQL
for i in range(5):
    legs = s.IC if i % 2 == 0 else s.STR
    sid = s.make(f'W2 Nine {i + 1}', legs)
    for t, a, p in legs:
        subprocess.run(PSQL + [f"insert into public.paper_orders (strategy_id, contract_id, side, quantity, price, kind, placed_at) select {sid}, c.id, '{a}', 65, {p}, 'open', '2026-11-27 10:15:00+05:30' from public.catalogue_contracts c where c.exchange_token={t} and c.exchange_segment='NSE_FO'"], env=s.ENV)
ids = [int(x) for x in subprocess.run(PSQL + ["select id from strategies where status<>'closed' and name not like '%Real%' order by id"], capture_output=True, text=True, env=s.ENV).stdout.split()]
for sid in ids:
    r = httpx.get(f'{s.BASE}/strategies/{sid}/adjustment-plan'); pbs = r.json().get('playbooks') or []
    if not pbs: print(sid, 'no playbook', r.status_code); continue
    r = httpx.post(f'{s.BASE}/strategies/{sid}/adjustment-plan', json={'playbook_id': pbs[0]['id'], 'accept': True}); print(sid, 'plan', r.status_code)
print('IDS', ids)
